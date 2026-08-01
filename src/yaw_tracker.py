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

from holo_patrol.cloud.alerts import EVIDENCE_URL_TTL_DAYS, AlertPayload, AlertThrottle
from holo_patrol.flight_control.offboard_guard import (
    OffboardGuard,
    build_zero_setpoint_stream,
)
from holo_patrol.flight_control.visual_servo import VisualServoController
from holo_patrol.perception.detection import Detection, TargetSelector
from holo_patrol.perception.target_state import TargetState

# --- 1. CONFIG AND CONTROL PARAMETERS ---
IMAGE_WIDTH = 1280
IMAGE_HEIGHT = 720

# Detection is only trusted for a short window after the last probe update; if the
# perception pipeline stalls (camera freeze, inference hang, GStreamer glitch) the
# control loop must fall back to a zero setpoint instead of repeating stale commands.
TARGET_TIMEOUT_S = 0.4

# --- 2. TESTED CORE COMPONENTS ---
# These are the exact same classes exercised by tests/test_visual_servo.py,
# tests/test_perception.py, tests/test_offboard_guard.py, and tests/test_alerts.py.
# enable_translation=False reproduces this script's yaw-only behavior exactly:
# forward and down are always forced to zero, matching docs/visual_servoing.md.
# Default VisualServoConfig() yaw parameters match this script's original
# gains/dead-zone, so behavior is unchanged.
target_selector = TargetSelector()
servo = VisualServoController(enable_translation=False)
offboard_guard = OffboardGuard()
alert_throttle = AlertThrottle(cooldown_s=15.0)

# --- GLOBAL SHARED STATE (bridges the DeepStream probe thread and the asyncio loop) ---
# A single reference assignment to this name is atomic in CPython (GIL-protected),
# so the control loop always reads one internally-consistent snapshot -- see
# holo_patrol.perception.target_state.TargetState for why this replaced five
# separate global variables.
global_target_state = TargetState.none()
global_ai_fps = 0.0

last_probe_time = time.time()
TARGET_IP = sys.argv[1] if len(sys.argv) > 1 else "local_ip(live connection)"

# --- 3. FIREBASE CONNECTION ---
try:
    # TODO: Replace with your actual Firebase service account key path
    cred = credentials.Certificate("path/to/your/firebase_key.json")

    # TODO: Replace with your actual Firebase Storage bucket URL
    firebase_admin.initialize_app(cred, {'storageBucket': 'your-project-id.appspot.com'})

    db = firestore.client()
    bucket = storage.bucket()
    print("✅ Firebase Infrastructure Active and Firestore Connected.")
except Exception as e:
    # Don't let a broken Firebase config fail silently: the drone will still fly
    # and track targets, but every alert upload below will be skipped and logged.
    db = None
    bucket = None
    print(f"❌ Firebase Connection Error: {e}")
    print("⚠️  Alerts will NOT be uploaded until this is fixed and the script is restarted.")


def send_alert_to_firebase(frame, track_id, confidence):
    """Uploads the evidence frame and writes the Firestore alert document.

    Payload shape comes from holo_patrol.cloud.alerts.AlertPayload, the same
    class covered by tests/test_alerts.py -- this is the actual detector
    confidence for this frame, not a hardcoded placeholder value.
    """
    if db is None or bucket is None:
        print(f"❌ [ALERT SKIPPED] ID:{track_id} — Firebase is not connected (see startup error above).")
        return

    try:
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        local_path = f"/tmp/alert_{timestamp_str}.jpg"
        cv2.imwrite(local_path, frame)

        blob = bucket.blob(f"alarm_images/{timestamp_str}.jpg")
        blob.upload_from_filename(local_path)
        url = blob.generate_signed_url(
            expiration=datetime.now() + timedelta(days=EVIDENCE_URL_TTL_DAYS)
        )

        payload = AlertPayload(
            title="🎯 Suspect Tracking Initiated",
            message=f"Drone locked onto human target with ID {track_id} and initiated autonomous tracking.",
            track_id=track_id,
            confidence=confidence,
            location_name="Drone Main Camera",
        )
        doc = payload.to_firestore_dict(image_url=url)
        doc["timestamp"] = firestore.SERVER_TIMESTAMP
        db.collection('alerts').document().set(doc)

        print(f"🚀 [ALERT] ID:{track_id} Image and Firestore data sent to Firebase!")

        if os.path.exists(local_path):
            os.remove(local_path)

    except Exception as e:
        print(f"❌ Firebase Upload Error: {e}")


# --- 4. DEEPSTREAM SINK PAD PROBE ---
def osd_sink_pad_buffer_probe(pad, info, u_data):
    """Extracts metadata from the GStreamer buffer and updates the shared target state."""
    global global_target_state, global_ai_fps
    global last_probe_time

    current_time = time.time()
    time_diff = current_time - last_probe_time
    if time_diff > 0:
        global_ai_fps = 1.0 / time_diff
    last_probe_time = current_time

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    # pyds' Python bindings take a buffer's `hash()` (its pointer identity) rather than
    # the GstBuffer object itself -- this is the documented pyds/DeepStream API, not a bug.
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list

    local_state = TargetState.none()

    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        n_frame = pyds.get_nvds_buf_surface(hash(gst_buffer), frame_meta.batch_id)
        frame_copy = np.array(n_frame, copy=True, order='C')
        frame_bgr = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)

        l_obj = frame_meta.obj_meta_list
        detections = []
        obj_meta_by_track_id = {}

        while l_obj is not None:
            try:
                obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break

            if obj_meta.class_id == 0:  # 'person' in this deployment's label map
                x1 = max(0, int(obj_meta.rect_params.left))
                y1 = max(0, int(obj_meta.rect_params.top))
                x2 = min(IMAGE_WIDTH, int(x1 + obj_meta.rect_params.width))
                y2 = min(IMAGE_HEIGHT, int(y1 + obj_meta.rect_params.height))
                det = Detection(
                    class_id=obj_meta.class_id,
                    confidence=obj_meta.confidence,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    track_id=obj_meta.object_id,
                )
                detections.append(det)
                obj_meta_by_track_id[det.track_id] = obj_meta
            else:
                # Hide bounding boxes for non-target classes
                obj_meta.rect_params.border_width = 0
                obj_meta.text_params.display_text = ""

            l_obj = l_obj.next

        best = target_selector.select(detections)

        trigger_alert = False
        alert_track_id = -1
        alert_confidence = 0.0

        if best is not None:
            local_state = TargetState(
                detected=True,
                center_x=best.center_x,
                center_y=best.center_y,
                height=best.height,
                track_id=best.track_id,
                detected_at=current_time,
            )

            best_obj = obj_meta_by_track_id[best.track_id]
            # Highlight the locked target in green
            best_obj.rect_params.border_color.set(0.0, 1.0, 0.0, 1.0)
            best_obj.rect_params.border_width = 4
            best_obj.text_params.display_text = f"TRACKING ID:{best.track_id} | FPS: {global_ai_fps:.1f}"
            best_obj.text_params.font_params.font_color.set(0.0, 1.0, 0.0, 1.0)

            if alert_throttle.should_send(current_time, track_id=best.track_id):
                trigger_alert = True
                alert_track_id = best.track_id
                alert_confidence = best.confidence

        if trigger_alert:
            threading.Thread(
                target=send_alert_to_firebase,
                args=(frame_bgr.copy(), alert_track_id, alert_confidence),
            ).start()
            alert_throttle.mark_sent(current_time, track_id=alert_track_id)

        l_frame = l_frame.next

    # Single atomic reference assignment -- see TargetState's docstring for why
    # this replaced five separately-written global variables.
    global_target_state = local_state
    return Gst.PadProbeReturn.OK


# --- 5. GSTREAMER BACKGROUND THREAD RUNNER ---
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
    try:
        async for flight_mode in drone.telemetry.flight_mode():
            mode_str = str(flight_mode)
            changed = offboard_guard.update_flight_mode(mode_str)
            if changed and offboard_guard.is_authorized():
                print("\n🔄 [YAW TEST] Autonomous Authorization Granted! Drone will lock onto target.")
            elif changed:
                print(f"\n⚠️ [MODE CHANGE] Control Transferred to PILOT. (Current Mode: {mode_str})")
    except Exception as e:
        print(f"❌ Mode Monitoring Error: {e}")
        # Losing the flight-mode stream means we can no longer trust that we still
        # hold Offboard authority; fail safe rather than keep issuing setpoints.
        offboard_guard.is_offboard = False


# --- 6. MAVSDK ASYNC FLIGHT AND CONTROL LOOP ---
async def run_mavsdk_loop():
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
        if offboard_guard.is_authorized():
            try:
                for setpoint in build_zero_setpoint_stream(count=10):
                    await drone.offboard.set_velocity_body(
                        VelocityBodyYawspeed(setpoint.forward, setpoint.right, setpoint.down, setpoint.yaw_rate)
                    )
                    await asyncio.sleep(0.05)
                await drone.offboard.start()
                print("✅ MAVSDK Setpoint Stream Started (Yaw Active).")
                break
            except OffboardError:
                print("⚠️ Failed to start Offboard, retrying...")
        await asyncio.sleep(0.5)

    # Tracking Loop
    while True:
        # Read the shared snapshot exactly once so the rest of this iteration acts
        # on one internally-consistent target, not several separately-read globals.
        target = global_target_state
        target_is_fresh = target.is_fresh(now=time.time(), timeout_s=TARGET_TIMEOUT_S)

        if offboard_guard.is_authorized() and target_is_fresh:
            # target_center_y, target_box_height, and relative_altitude_m are unused
            # by the control law here: enable_translation=False makes compute_setpoint
            # skip forward/down entirely and only compute yaw_rate from target_center_x.
            setpoint = servo.compute_setpoint(
                target_center_x=target.center_x,
                target_center_y=target.center_y,
                target_box_height=target.height,
                relative_altitude_m=0.0,
            )

            print(
                f"🎯 [YAW TRACKING] ID:{target.track_id} | Speed: 0.0 m/s | "
                f"Turn: {setpoint.yaw_rate:.2f} deg/s | AI: {global_ai_fps:.1f} FPS"
            )

            try:
                await drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(setpoint.forward, setpoint.right, setpoint.down, setpoint.yaw_rate)
                )
            except Exception:
                offboard_guard.is_offboard = False

        else:
            # Hover in place / stop rotation if target is lost or Offboard is not authorized
            zero = servo.zero_setpoint()
            try:
                await drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(zero.forward, zero.right, zero.down, zero.yaw_rate)
                )
            except Exception:
                offboard_guard.is_offboard = False

        await asyncio.sleep(0.05)


# --- 7. PIPELINE CONFIGURATION AND MAIN ENTRY ---
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
