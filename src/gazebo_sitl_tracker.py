import asyncio
import os
import threading
import time
from datetime import datetime, timedelta

import cv2
import firebase_admin
from firebase_admin import credentials, firestore, storage
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed
from ultralytics import YOLO

from holo_patrol.cloud.alerts import EVIDENCE_URL_TTL_DAYS
from holo_patrol.flight_control.visual_servo import VisualServoConfig, VisualServoController

# NOTE: This script is a Gazebo/PX4 SITL simulation prototype only. It predates
# the tested holo_patrol.flight_control.visual_servo altitude-protection logic
# (see §3.2 below) and must NOT be used to fly a real vehicle as-is.

# Only the (tested) NaN/at-the-floor descent guard from VisualServoController is reused
# here -- the bang-bang dive/climb thresholds below are this prototype's own design and
# are kept as-is so the Gazebo-vs-real-flight comparison in docs/visual_servoing.md §8
# still holds. min_safe_altitude_m matches this script's own "climb back up" threshold.
_altitude_guard = VisualServoController(config=VisualServoConfig(min_safe_altitude_m=3.5))

# --- FIREBASE CONFIGURATION ---
try:
    # TODO: Replace 'your_firebase_key.json' with your own Firebase service account key path
    cred = credentials.Certificate("your_firebase_key.json")
    
    # TODO: Replace with your actual Firebase Storage bucket URL
    firebase_admin.initialize_app(cred, {'storageBucket': 'your-project-id.appspot.com'})
    
    db = firestore.client()
    bucket = storage.bucket()
    print("✅ Firebase connection is ready!")
except Exception as e:
    print(f"❌ Failed to initialize Firebase: {e}")


def process_and_upload_alert(frame_copy, confidence):
    """Saves a record to the database and uploads the captured image."""
    try:
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        local_path = f"temp_alert_{timestamp_str}.jpg"
        cv2.imwrite(local_path, frame_copy)

        blob = bucket.blob(f"alert_images/{timestamp_str}.jpg")
        blob.upload_from_filename(local_path)
        # Signed, time-limited URL instead of a permanently public one -- evidence
        # images should not be indefinitely accessible to anyone with the link.
        url = blob.generate_signed_url(
            expiration=datetime.now() + timedelta(days=EVIDENCE_URL_TTL_DAYS)
        )

        db.collection('alerts').document().set({
            "title": "Suspect Tracking Initiated",
            "message": "Drone detected a suspect and started tracking!",
            "isActive": True,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "imageURL": url,
            "confidence": float(confidence)
        })
        print("✅ Tracking Alert sent to the mobile app!")
        
        if os.path.exists(local_path): 
            os.remove(local_path)
            
    except Exception as e:
        print(f"❌ Upload Error: {e}")


# --- MAIN ASYNC LOOP (DRONE CONTROL + CAMERA) ---
async def run():
    print("Connecting to drone...")
    drone = System()
    
    # Connect to the drone via UDP (SITL or Companion Computer standard port)
    await drone.connect(system_address="udpin://127.0.0.1:14540")

    async for state in drone.core.connection_state():
        if state.is_connected:
            print("✅ Successfully connected to the drone!")
            break

    # --- ALTITUDE TRACKING RADAR ---
    # Async task that continuously reads the real-time altitude of the drone in the background.
    # Altitude is unknown until the first valid telemetry sample arrives. Do NOT assume a
    # safe default value here: an assumed altitude that is wrong (e.g. the drone is actually
    # much lower than assumed) could let a descent command through the safety floor below --
    # see the same pattern in visual_tracker_3d.py.
    drone_altitude = None
    altitude_valid = False

    async def monitor_altitude():
        nonlocal drone_altitude, altitude_valid
        async for position in drone.telemetry.position():
            drone_altitude = position.relative_altitude_m
            altitude_valid = True

    # Start the altitude radar in the background
    asyncio.create_task(monitor_altitude())
    # ---------------------------------------------

    print("Loading YOLOv8 model...")
    model = YOLO('yolov8s.pt')

    # GStreamer pipeline for video capture (Modify port/payload according to your setup)
    pipeline = "udpsrc port=5600 ! application/x-rtp, payload=96 ! rtph264depay ! avdec_h264 ! videoconvert ! appsink drop=true sync=false"
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    cv2.namedWindow("Drone_Tracking_Camera", cv2.WINDOW_NORMAL)

    last_alert_time = 0
    is_tracking = False

    print("System ready. Start the patrol from QGroundControl...")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: 
            break
            
        frame = cv2.resize(frame, (640, 480))

        frame_height, frame_width = frame.shape[:2]
        center_x_image = frame_width // 2

        results = model(frame, verbose=False)
        person_detected = False
        highest_conf = 0.0
        best_box = None

        MIN_CONFIDENCE = 0.62  # Requires at least 62% confidence before locking on target

        for result in results:
            for box in result.boxes:
                # Class 0 corresponds to 'person' in the COCO dataset
                if int(box.cls[0]) == 0:
                    conf = float(box.conf[0])
                    if conf > highest_conf and conf > MIN_CONFIDENCE:
                        highest_conf = round(conf, 2)
                        best_box = box
                        person_detected = True

        if person_detected:
            x1, y1, x2, y2 = map(int, best_box.xyxy[0])
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            person_center_x = (x1 + x2) // 2
            person_height = y2 - y1

            # --- OVERRIDE STEERING OPERATION ---
            if not is_tracking:
                print("🚨 Target Found! Canceling mission (Hold)...")
                try:
                    await drone.action.hold()
                    await asyncio.sleep(1.0)

                    print("Preparing for offboard mode...")
                    # Send initial setpoints before starting offboard mode (px4 requirement)
                    for _ in range(15):
                        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
                        await asyncio.sleep(0.05)

                    await drone.offboard.start()
                    is_tracking = True
                    print("✅ CONTROL ACQUIRED! Autonomous diving and tracking initiated.")
                except Exception as e:
                    print(f"❌ Failed to switch to tracking mode: {e}")

            # --- TRACKING (VISUAL SERVO) CONTROL ---
            if is_tracking:
                # Faster and more stable reflexes
                YAW_K = 0.015
                FORWARD_K = 0.025  # Forward movement coefficient increased
                TARGET_HEIGHT = 350

                error_x = person_center_x - center_x_image
                error_y = TARGET_HEIGHT - person_height

                # RIGHT/LEFT TURN (with Deadzone implementation)
                if abs(error_x) < 40:
                    yaw_speed = 0.0
                else:
                    yaw_speed = error_x * YAW_K

                # FORWARD/BACKWARD SPEED
                if abs(error_y) < 30:
                    forward_speed = 0.0
                else:
                    forward_speed = error_y * FORWARD_K

                # --- DIVE (ALTITUDE) CONTROL ---
                if not altitude_valid:
                    # Altitude telemetry hasn't arrived yet -- do not assume it is
                    # safe to dive. Hold vertical position instead of guessing.
                    down_speed = 0.0
                else:
                    down_speed = 0.0
                    if drone_altitude > 4.5:
                        down_speed = 1.0  # Glide down at 1 m/s (Dive)
                    elif drone_altitude < 3.5:
                        down_speed = -0.5  # Gently pull up nose if dropped below 3.5 meters

                # Defense-in-depth: reuse the tested floor/NaN guard even though the
                # thresholds above already respect it, and to safely handle a
                # corrupted (NaN) telemetry sample.
                down_speed = _altitude_guard.apply_altitude_protection(
                    down_speed,
                    relative_altitude_m=drone_altitude if altitude_valid else float("nan"),
                )

                # EXPANDED LIMITS (For Faster Tracking)
                forward_speed = max(min(forward_speed, 3.0), -0.5)  # Max speed increased to 3.0 m/s (~11 km/h)
                yaw_speed = max(min(yaw_speed, 20.0), -20.0)

                altitude_label = f"{drone_altitude:.1f} m" if altitude_valid else "N/A"
                print(f"🎯 LOCK: Speed={forward_speed:.2f} m/s | Altitude={altitude_label} | Dive={down_speed:.1f} m/s")

                # Send command to drone: Forward, Yaw (turn), and Downward speed
                await drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(forward_speed, 0.0, down_speed, yaw_speed)
                )

            current_time = time.time()
            if current_time - last_alert_time > 15:
                # Trigger background thread for DB upload to prevent blocking the video feed
                threading.Thread(target=process_and_upload_alert, args=(frame.copy(), highest_conf)).start()
                last_alert_time = current_time

        else:
            # Hover in place if the target (person) is lost
            if is_tracking:
                await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))

        cv2.imshow("Drone_Tracking_Camera", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        await asyncio.sleep(0.02)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    asyncio.run(run())