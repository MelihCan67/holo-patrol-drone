import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
import pyds
import time
import threading
import asyncio
import firebase_admin
import cv2
import numpy as np
from firebase_admin import credentials, firestore, storage
from datetime import datetime, timedelta
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed, OffboardError

# --- 1. CONFIG VE KONTROL PARAMETRELERİ ---
ALERT_SAVE_COOLDOWN = 15
IMAGE_WIDTH = 1280
IMAGE_HEIGHT = 720
IMAGE_CENTER_X = IMAGE_WIDTH // 2
IMAGE_CENTER_Y = IMAGE_HEIGHT // 2  

# P-Kontrolör (Görsel Servo) 3D Ayarları (AGRESİF VE KARARLI)
TARGET_BOX_HEIGHT = 300   # Hedefle aradaki ideal mesafe
OLU_BOLGE_X = 40          # Sağ/Sol (Yaw) titreme payı
OLU_BOLGE_MESAFE = 30     # İleri/Geri titreme payı
OLU_BOLGE_Y = 35          # Aşağı/Yukarı (Alçalma) titreme payı

YAW_K = 0.035             # Dönüş katsayısı (Hızlandırıldı)
FORWARD_K = 0.018         # Yaklaşma katsayısı (Hızlandırıldı)
DOWN_K = 0.008           # Alçalma katsayısı (Hızlandırıldı)

MIN_SAFE_ALTITUDE = 3.0   # KESİN ALT LİMİT (Metre)

# --- GLOBAL PAYLAŞILAN VERİLER ---
global_target_detected = False
global_error_x = 0
global_error_y = 0        
global_person_height = 0
global_track_id = -1
global_ai_fps = 0.0       
global_is_offboard = False  
global_altitude = 10.0    

last_probe_time = time.time()
HEDEF_IP = sys.argv[1] if len(sys.argv) > 1 else "172.20.10.13"

# --- 2. FIREBASE BAĞLANTISI ---
try:
    cred = credentials.Certificate("/home/melih/Workspace/DeepStream-Yolo/firebase_key.json")
    firebase_admin.initialize_app(cred, {'storageBucket': 'dronesecurityalert.firebasestorage.app'})
    db = firestore.client()
    bucket = storage.bucket()
    print("✅ Firebase Altyapısı ve Canlı Uyarı Sistemi AKTİF.")
except Exception as e:
    print(f"❌ Firebase Bağlantı Hatası: {e}")

last_alert_save_time = 0

def send_alert_to_firebase(frame, track_id):
    try:
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        local_path = f"/tmp/alert_{timestamp_str}.jpg"
        cv2.imwrite(local_path, frame) 
        
        blob = bucket.blob(f"alarm_images/{timestamp_str}.jpg")
        blob.upload_from_filename(local_path)
        url = blob.generate_signed_url(expiration=datetime.now() + timedelta(days=1825))
        
        db.collection('alerts').document().set({
            "title": "🚨 HEDEF TAKİBİ BAŞLADI",
            "message": f"Dron, ID {track_id} hedefini tespit etti. Yaklaşma ve 3D takip manevrası devrede.",
            "timestamp": firestore.SERVER_TIMESTAMP, 
            "imageURL": url,
            "id": int(track_id),
            "locationName": "Drone Ana Kamera",
            "severity": "critical",
            "isActive": True,
            "confidence": 0.95
        })
        print(f"🚀 [FIREBASE] ID:{track_id} hedefinin verileri merkeze iletildi!")
        import os
        if os.path.exists(local_path): os.remove(local_path)
    except Exception as e:
        print(f"❌ Firebase Aktarım Hatası: {e}")

# --- 3. DEEPSTREAM SONDA (PROBE) ---
def osd_sink_pad_buffer_probe(pad, info, u_data):
    global global_target_detected, global_error_x, global_error_y, global_person_height
    global_track_id, global_ai_fps, last_probe_time, last_alert_save_time
    
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

            if obj_meta.class_id == 0:
                if obj_meta.confidence > highest_conf:
                    highest_conf = obj_meta.confidence
                    best_obj = obj_meta
            else:
                obj_meta.rect_params.border_width = 0
                obj_meta.text_params.display_text = ""

            l_obj = l_obj.next

        if best_obj is not None:
            local_detected = True
            track_id = best_obj.object_id
            
            x1 = max(0, int(best_obj.rect_params.left))
            y1 = max(0, int(best_obj.rect_params.top))
            x2 = min(IMAGE_WIDTH, int(x1 + best_obj.rect_params.width))
            y2 = min(IMAGE_HEIGHT, int(y1 + best_obj.rect_params.height))
            
            # 3D Uzay Verilerini Çıkar
            person_center_x = (x1 + x2) // 2
            global_error_x = person_center_x - IMAGE_CENTER_X
            
            person_center_y = (y1 + y2) // 2
            global_error_y = person_center_y - IMAGE_CENTER_Y

            global_person_height = y2 - y1
            global_track_id = track_id

            # Canlı OSD
            best_obj.rect_params.border_color.set(1.0, 0.5, 0.0, 1.0) 
            best_obj.rect_params.border_width = 4
            best_obj.text_params.display_text = f"3D LOCK ID:{track_id} | ALT:{global_altitude:.1f}m"
            best_obj.text_params.font_params.font_color.set(1.0, 0.5, 0.0, 1.0)

            # Firebase Tetikleyici (15 saniyede bir)
            if time.time() - last_alert_save_time > ALERT_SAVE_COOLDOWN:
                trigger_alert = True
                alert_track_id = track_id

        if trigger_alert:
            # Görüntüyü arka planda Firebase'e yükle
            threading.Thread(target=send_alert_to_firebase, args=(frame_bgr.copy(), alert_track_id)).start()
            last_alert_save_time = time.time()

        l_frame = l_frame.next

    global_target_detected = local_detected
    return Gst.PadProbeReturn.OK

# --- 4. GSTREAMER BACKGROUND THREAD ---
def start_gstreamer_pipeline(pipeline):
    print("🚀 GStreamer Canlı Yayın (3D TAM KONTROL) Başlatılıyor...")
    pipeline.set_state(Gst.State.PLAYING)
    loop = GLib.MainLoop()
    try:
        loop.run()
    except Exception as e:
        print(f"GStreamer Döngü Hatası: {e}")

# --- ARKA PLAN UÇUŞ MODU DİNLEYİCİSİ ---
async def monitor_flight_mode(drone):
    global global_is_offboard
    try:
        async for flight_mode in drone.telemetry.flight_mode():
            mode_str = str(flight_mode).upper()
            if "OFFBOARD" in mode_str or "GUIDED" in mode_str:
                if not global_is_offboard:
                    print("\n🚀 [3D UÇUŞ] Otonom Yetki Verildi! Hedefe kilitleniliyor.")
                    global_is_offboard = True
            else:
                if global_is_offboard:
                    print(f"\n⚠️ [MOD DEĞİŞİMİ] Kontrol PİLOTA Devredildi. (Mevcut Mod: {mode_str})")
                    global_is_offboard = False
    except Exception as e:
        print(f"❌ Mod Dinleme Hatası: {e}")

# --- ARKA PLAN İRTİFA (ALTITUDE) DİNLEYİCİSİ ---
async def monitor_telemetry(drone):
    global global_altitude
    try:
        async for position in drone.telemetry.position():
            global_altitude = position.relative_altitude_m
    except Exception:
        pass

# --- 5. MAVSDK ASENKRON 3D KONTROL DÖNGÜSÜ ---
async def run_mavsdk_loop():
    global global_target_detected, global_error_x, global_error_y, global_person_height
    global_track_id, global_ai_fps, global_is_offboard, global_altitude
    
    print("🛰️ Pixhawk Kontrolcüsüne Bağlanılıyor (UART ttyTHS1 - 115200)...")
    drone = System()
    await drone.connect(system_address="serial:///dev/ttyTHS1:115200")

    async for state in drone.core.connection_state():
        if state.is_connected:
            print("🔗 Pixhawk Bağlantısı Kusursuz Sağlandı!")
            break

    print("🔒 Güvenlik Kilidi Aktif: Devriye anında veya manuelken şalteri 'Offboard' yapmanız bekleniyor...")

    asyncio.ensure_future(monitor_flight_mode(drone))
    asyncio.ensure_future(monitor_telemetry(drone))
    
    while True:
        if global_is_offboard:
            try:
                for _ in range(10):
                    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
                    await asyncio.sleep(0.05)
                await drone.offboard.start()
                print("✅ MAVSDK 3D Setpoint Akışı Başladı.")
                break
            except OffboardError:
                pass
        await asyncio.sleep(0.5)

    while True:
        if global_is_offboard and global_target_detected:
            
            # 1. YAW (Dönüş) Hesaplaması
            if abs(global_error_x) < OLU_BOLGE_X:
                yaw_speed = 0.0
            else:
                yaw_speed = global_error_x * YAW_K

            # 2. İLERİ/GERİ (Yaklaşma) Hesaplaması
            error_distance = TARGET_BOX_HEIGHT - global_person_height
            if abs(error_distance) < OLU_BOLGE_MESAFE:
                forward_speed = 0.0
            else:
                forward_speed = error_distance * FORWARD_K

            # 3. AŞAĞI/YUKARI (Alçalma/Tırmanma) Hesaplaması
            if abs(global_error_y) < OLU_BOLGE_Y:
                down_speed = 0.0
            else:
                down_speed = global_error_y * DOWN_K

            # --- SIKIYÖNETİM LİMİTLERİ (Agresif ama Güvenli) ---
            forward_speed = max(min(forward_speed, 1.5), -1.0) # İleri 1.5m/s (hızlandı), Geri -1.0m/s
            yaw_speed = max(min(yaw_speed, 30.0), -30.0)       # Dönüş 30 derece/s
            down_speed = max(min(down_speed, 0.5), -0.5)       # Dikey 0.5 m/s sabit güvenlik
            
            # --- 3 METRE YERE ÇAKILMA KİLİDİ ---
            if global_altitude <= MIN_SAFE_ALTITUDE and down_speed > 0:
                down_speed = 0.0
                limit_msg = " [!ALT LIMIT!]"
            else:
                limit_msg = ""

            print(f"🎯 ID:{global_track_id} | İleri: {forward_speed:.2f} | Alçalma: {down_speed:.2f}{limit_msg} | Yaw: {yaw_speed:.2f} | Alt: {global_altitude:.1f}m")
            
            try:
                await drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(forward_speed, 0.0, down_speed, yaw_speed)
                )
            except Exception:
                pass

        else:
            try:
                await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            except Exception:
                pass

        await asyncio.sleep(0.05) 

# --- 6. PIPELINE YAPILANDIRMASI VE MAIN ENTRY ---
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
    pgie.set_property('config-file-path', "/home/melih/Workspace/DeepStream-Yolo/config_infer_primary_yoloV8.txt")

    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    tracker.set_property('tracker-width', 320)
    tracker.set_property('tracker-height', 192)
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
    sink.set_property('host', HEDEF_IP) 
    sink.set_property('port', 5000)
    sink.set_property('sync', False) 
    sink.set_property('async', False)

    pipeline.add(source); pipeline.add(streammux); pipeline.add(pgie); pipeline.add(tracker)
    pipeline.add(nvvidconv1); pipeline.add(capsfilter); pipeline.add(nvosd); pipeline.add(nvvidconv2)
    pipeline.add(encoder); pipeline.add(rtppay); pipeline.add(sink)

    sinkpad = streammux.get_request_pad("sink_0")
    srcpad = source.get_static_pad("src")
    srcpad.link(sinkpad)
    
    streammux.link(pgie); pgie.link(tracker); tracker.link(nvvidconv1)   
    nvvidconv1.link(capsfilter); capsfilter.link(nvosd); nvosd.link(nvvidconv2)
    nvvidconv2.link(encoder); encoder.link(rtppay); rtppay.link(sink)

    osd_sink_pad = nvosd.get_static_pad("sink")
    osd_sink_pad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    gst_thread = threading.Thread(target=start_gstreamer_pipeline, args=(pipeline,), daemon=True)
    time.sleep(2)
    gst_thread.start()

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_mavsdk_loop())
    except KeyboardInterrupt:
        print("\nSistem Kapatılıyor...")
        pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    main()
