import sys

import gi

gi.require_version('Gst', '1.0')
import asyncio
import os
import threading
import time
from datetime import datetime, timedelta

import cv2
import firebase_admin
import numpy as np
import pyds
from firebase_admin import credentials, firestore, storage
from gi.repository import GLib, Gst
from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed

# --- 1. CONFIG AND CONTROL PARAMETERS ---
ALERT_SAVE_COOLDOWN = 15
IMAGE_WIDTH = 1280
IMAGE_HEIGHT = 720
IMAGE_CENTER_X = IMAGE_WIDTH // 2

# P-Controller (YAW / TURN ONLY)
DEAD_ZONE_X = 40          # Margin to prevent left/right jitter (in pixels)
YAW_K = 0.035             # Proportional gain for yaw (Very stable and fast response)
MAX_YAW_DEG_SEC = 30.0    # Maximum yaw rate (30 degrees per second)

# --- GLOBAL SHARED VARIABLES ---
global_target_detected = False
global_error_x = 0
global_track_id = -1
global_ai_fps = 0.0       
global_is_offboard = False  

last_probe_time = time.time()
TARGET_IP = sys.argv[1] if len(sys.argv) > 1 else "local_ip(live connection)"

# --- 2. FIREBASE CONNECTION ---
try:
    # TODO: Replace with your actual Firebase service account key path
    cred = credentials.Certificate("path/to/your/firebase_key.json")
    
    # TODO: Replace with your actual Firebase Storage bucket URL
    firebase_admin.initialize_app(cred, {'storageBucket': 'your-project-id.appspot.com'})
    
    db = firestore.client()
    bucket = storage.bucket()
    print("✅ Firebase Infrastructure Active and Firestore Connected.")
except Exception as e:
    print(f"❌ Firebase Connection Error: {e}")

last_alert_save_time = 0

def send_alert_to_firebase(frame, track_id):
    """Saves the alert to Firestore and uploads the frame to Cloud Storage."""
    try:
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        local_path = f"/tmp/alert_{timestamp_str}.jpg"
        cv2.imwrite(local_path, frame) 
        
        blob = bucket.blob(f"alarm_images/{timestamp_str}.jpg")
        blob.upload_from_filename(local_path)
        url = blob.generate_signed_url(expiration=datetime.now() + timedelta(days=1825))
        
        db.collection('alerts').document().set({
            "title": "🎯 Suspect Tracking Initiated",
            "message": f"Drone locked onto human target with ID {track_id} and initiated autonomous tracking.",
            "timestamp": firestore.SERVER_TIMESTAMP, 
            "imageURL": url,
            "id": int(track_id),
            "locationName": "Drone Main Camera",
            "severity": "critical",
            "isActive": True,
            "confidence": 0.95
        })
        print(f"🚀 [ALERT] ID:{track_id} Image and Firestore data sent to Firebase!")
        
        if os.path.exists(local_path): 
            os.remove(local_path)
            
    except Exception as e:
        print(f"❌ Firebase Upload Error: {e}")

# --- 3. DEEPSTREAM SINK PAD PROBE ---
def osd_sink_pad_buffer_probe(pad, info, u_data):
    """Extracts metadata from the GStreamer buffer and computes target tracking errors."""
    global global_target_detected, global_error_x, global_track_id, global_ai_fps, last_probe_time, last_alert_save_time
    
    current_time = time.time()
    time_diff = current_time - last_probe_time
    if time_diff > 0:
        global_ai_fps = 1.0 / time_diff
    last_probe_time = current_time

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list

    local_detected = False

    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        n_frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
        frame_copy = np.array(n_frame, copy=True, order='C')
        frame_bgr = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)

        l_obj = frame_meta.obj_meta_list
        highest_conf = 0
        best_obj = None
        trigger_alert = False
        alert_track_id = -1

        while l_obj is not None:
            try:
                obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break

            # Class ID 0 is generally 'person'
            if obj_meta.class_id == 0:
                if obj_meta.confidence > highest_conf:
                    highest_conf = obj_meta.confidence
                    best_obj = obj_meta
            else:
                # Hide bounding boxes for non-target classes
                obj_meta.rect_params.border_width = 0
                obj_meta.text_params.display_text = ""

            l_obj = l_obj.next

        if best_obj is not None:
            local_detected = True
            track_id = best_obj.object_id
            
            x1 = max(0, int(best_obj.rect_params.left))
            x2 = min(IMAGE_WIDTH, int(x1 + best_obj.rect_params.width))
            y1 = max(0, int(best_obj.rect_params.top))
            y2 = min(IMAGE_HEIGHT, int(y1 + best_obj.rect_params.height))
            
            person_center_x = (x1 + x2) // 2
            global_error_x = person_center_x - IMAGE_CENTER_X
            global_track_id = track_id

            # Highlight the locked target in green
            best_obj.rect_params.border_color.set(0.0, 1.0, 0.0, 1.0) 
            best_obj.rect_params.border_width = 4
            best_obj.text_params.display_text = f"TRACKING ID:{track_id} | FPS: {global_ai_fps:.1f}"
            best_obj.text_params.font_params.font_color.set(0.0, 1.0, 0.0, 1.0)

            # Firebase Alert Trigger
            if time.time() - last_alert_save_time > ALERT_SAVE_COOLDOWN:
                trigger_alert = True
                alert_track_id = track_id

        if trigger_alert:
            threading.Thread(target=send_alert_to_firebase, args=(frame_bgr.copy(), alert_track_id)).start()
            last_alert_save_time = time.time()

        l_frame = l_frame.next

    global_target_detected = local_detected
    return Gst.PadProbeReturn.OK

# --- 4. GSTREAMER BACKGROUND THREAD RUNNER ---
def start_gstreamer_pipeline(pipeline):
    print("🚀 Starting GStreamer Live Stream (YAW TEST MODE)...")
    pipeline.set_state(Gst.State.PLAYING)
    loop = GLib.MainLoop()
    try:
        loop.run()
    except Exception as e:
        print(f"GStreamer Loop Error: {e}")

# --- BACKGROUND FLIGHT MODE MONITOR ---
async def monitor_flight_mode(drone):
    """Monitors flight mode changes and enables offboard control logic."""
    global global_is_offboard
    try:
        async for flight_mode in drone.telemetry.flight_mode():
            mode_str = str(flight_mode).upper()
            if "OFFBOARD" in mode_str or "GUIDED" in mode_str:
                if not global_is_offboard:
                    print("\n🔄 [YAW TEST] Autonomous Authorization Granted! Drone will lock onto target.")
                    global_is_offboard = True
            else:
                if global_is_offboard:
                    print(f"\n⚠️ [MODE CHANGE] Control Transferred to PILOT. (Current Mode: {mode_str})")
                    global_is_offboard = False
    except Exception as e:
        print(f"❌ Mode Monitoring Error: {e}")

# --- 5. MAVSDK ASYNC FLIGHT AND CONTROL LOOP ---
async def run_mavsdk_loop():
    global global_target_detected, global_error_x, global_track_id, global_ai_fps, global_is_offboard
    
    print("🛰️ Connecting to Pixhawk Controller (UART ttyTHS1 - 115200)...")
    drone = System()
    # Ensure this port matches your companion computer to flight controller connection
    await drone.connect(system_address="serial:///dev/ttyTHS1:115200")

    async for state in drone.core.connection_state():
        if state.is_connected:
            print("🔗 Pixhawk Connection Successfully Established!")
            break

    print("🔒 Safety Lock Active: Waiting for flight mode to be set to 'Offboard'...")

    asyncio.ensure_future(monitor_flight_mode(drone))
    
    # Wait for offboard authorization
    while True:
        if global_is_offboard:
            try:
                # Send initial setpoints before starting offboard mode
                for _ in range(10):
                    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
                    await asyncio.sleep(0.05)
                await drone.offboard.start()
                print("✅ MAVSDK Setpoint Stream Started (Yaw Active).")
                break
            except OffboardError:
                print("⚠️ Failed to start Offboard, retrying...")
        await asyncio.sleep(0.5)

    # Tracking Loop
    while True:
        if global_is_offboard and global_target_detected:
            
            # Apply Deadzone
            if abs(global_error_x) < DEAD_ZONE_X:
                yaw_speed = 0.0
            else:
                yaw_speed = global_error_x * YAW_K

            # Clamp Yaw Speed
            yaw_speed = max(min(yaw_speed, MAX_YAW_DEG_SEC), -MAX_YAW_DEG_SEC)       

            print(f"🎯 [YAW TRACKING] ID:{global_track_id} | Speed: 0.0 m/s | Turn: {yaw_speed:.2f} deg/s | AI: {global_ai_fps:.1f} FPS")
            
            try:
                await drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(0.0, 0.0, 0.0, yaw_speed)
                )
            except Exception:
                pass

        else:
            # Hover in place / stop rotation if target is lost
            try:
                await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            except Exception:
                pass

        await asyncio.sleep(0.05)

# --- 6. PIPELINE CONFIGURATION AND MAIN ENTRY ---
def main():
    Gst.init(None)
    pipeline = Gst.Pipeline()

    source = Gst.ElementFactory.make("nvarguscamerasrc", "camera-source")
    source.set_property('bufapi-version', True)

    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    streammux.set_property('width', IMAGE_WIDTH)
    streammux.set_property('height', IMAGE_HEIGHT)
    streammux.set_property('batch-size', 1)
    streammux.set_property('live-source', 1)

    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    # TODO: Replace with your actual DeepStream YOLO config path
    pgie.set_property('config-file-path', "path/to/your/config_infer_primary_yoloV8.txt")

    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    tracker.set_property('tracker-width', 320)
    tracker.set_property('tracker-height', 192)
    # Default Jetpack / DeepStream SDK paths
    tracker.set_property('ll-lib-file', '/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so')
    tracker.set_property('ll-config-file', '/opt/nvidia/deepstream/deepstream/samples/configs/deepstream-app/config_tracker_IOU.yml')

    nvvidconv1 = Gst.ElementFactory.make("nvvideoconvert", "convertor1")
    caps = Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA")
    capsfilter = Gst.ElementFactory.make("capsfilter", "capsfilter")
    capsfilter.set_property("caps", caps)

    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    nvvidconv2 = Gst.ElementFactory.make("nvvideoconvert", "convertor2")
    
    encoder = Gst.ElementFactory.make("nvv4l2h264enc", "h264-encoder")
    encoder.set_property('bitrate', 2000000) 
    encoder.set_property('insert-sps-pps', 1)
    
    rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
    sink = Gst.ElementFactory.make("udpsink", "udpsink")
    sink.set_property('host', TARGET_IP) 
    sink.set_property('port', 5000)
    sink.set_property('sync', False) 
    sink.set_property('async', False)

    # Build Pipeline
    pipeline.add(source); pipeline.add(streammux); pipeline.add(pgie); pipeline.add(tracker)
    pipeline.add(nvvidconv1); pipeline.add(capsfilter); pipeline.add(nvosd); pipeline.add(nvvidconv2)
    pipeline.add(encoder); pipeline.add(rtppay); pipeline.add(sink)

    # Link Elements
    sinkpad = streammux.get_request_pad("sink_0")
    srcpad = source.get_static_pad("src")
    srcpad.link(sinkpad)
    
    streammux.link(pgie); pgie.link(tracker); tracker.link(nvvidconv1)   
    nvvidconv1.link(capsfilter); capsfilter.link(nvosd); nvosd.link(nvvidconv2)
    nvvidconv2.link(encoder); encoder.link(rtppay); rtppay.link(sink)

    # Add Probe
    osd_sink_pad = nvosd.get_static_pad("sink")
    osd_sink_pad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    # Start GStreamer in a separate thread
    gst_thread = threading.Thread(target=start_gstreamer_pipeline, args=(pipeline,), daemon=True)
    time.sleep(2)
    gst_thread.start()

    # Start MAVSDK Async Loop
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_mavsdk_loop())
    except KeyboardInterrupt:
        print("\nShutting down system...")
        pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    main()