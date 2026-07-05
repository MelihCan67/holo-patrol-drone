# 🚁 HOLO-PATROL: Autonomous Security Patrol Drone

# 🚁 HOLO-PATROL: Autonomous Security Patrol Drone

[![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)](https://www.python.org/)
[![NVIDIA DeepStream](https://img.shields.io/badge/NVIDIA-DeepStream-76B900.svg)](https://developer.nvidia.com/deepstream-sdk)
[![MAVSDK](https://img.shields.io/badge/MAVSDK-Dronecode-1E4E8C.svg)](https://mavsdk.mavlink.io/)
[![Firebase](https://img.shields.io/badge/Firebase-Cloud-FFCA28.svg)](https://firebase.google.com/)

**Real-time onboard face recognition · 3D Visual Servoing · Jetson Nano · MAVSDK · Firebase Mobile Integration**
      
Bachelor's thesis project — Başkent University, Department of Computer Engineering, 2026  
**Authors:** Melih Can Kesgin, Mehmet Ali Karaca, Doğa Küçükkayalar, Ecem Dilan Ayaz, Sude Yencilek  
**Advisor:** Asst. Prof. Dr. İclal Çetin Taş  
**Supported by:** TürkTrust  

<!-- GÖRSEL 1: BURAYA DRONUN VEYA POSTERİNİN YÜKSEK KALİTELİ BİR FOTOĞRAFINI EKLE -->
![Holo-Patrol Drone on the Field](media/cover_photo.jpg)

## 📺 Field Validation & Demo

<!-- GÖRSEL 2: BURAYA UÇUŞ VE HEDEF TAKİBİ YAPAN KISA BİR GIF EKLE -->
![3D Visual Servoing and Target Lock](media/flight_demo.gif)

## 🚀 Motivation & Overview

Traditional security systems rely heavily on static camera networks or manual drone patrols, which are susceptible to human error and response delays. **HOLO-PATROL** was engineered to bridge this gap by introducing a fully autonomous, proactive aerial security solution aligned with the UN Sustainable Development Goal 9 (Industry, Innovation and Infrastructure)[cite: 1].

This repository presents an end-to-end autonomous UAV security ecosystem. Operating on a Holybro X500 V2 frame, the system uses an NVIDIA Jetson Nano as a companion computer to process aerial video. When an unauthorized entry or an unrecognized face is detected during a routine patrol mission, the AI subsystem overrides the flight controller via MAVSDK (Offboard mode) to autonomously track the target in 3D space. Simultaneously, high-resolution evidence is transmitted to a custom mobile application via Firebase.

## 🎯 Operational Workflow

The system operates in a decoupled, multi-stage workflow:
1. **Routine Patrol:** The UAV executes a predefined GPS-based geofenced patrol via QGroundControl (Mission Mode), sustaining operations for approximately 15-20 minutes per mission[cite: 1].
2. **Threat Detection:** The onboard Jetson Nano continuously runs YOLOv8 and facial recognition pipelines on the live camera feed.
3. **AI Override & Target Lock:** Upon detecting a threat, the Jetson takes command via UART, engaging Offboard mode. It tracks the target dynamically using 3D Visual Servoing.
4. **Cloud Alert:** Evidence frames and telemetry are pushed to Firebase, triggering instant notifications on the mobile security dashboard.
5. **Resume Patrol:** Once the threat is cleared or the operator toggles the RC switch, the drone safely halts and awaits the command to resume its original geofenced route.

## 🌟 Key Highlights

* **Full UAV Hardware & AI Integration:** Holybro X500 V2 UAV platform synchronized with a Pixhawk 6C flight controller and Jetson Nano.
* **Advanced Face Verification:** Utilizes a Dlib HOG-based face detector paired with FaceNet to extract 128-dimensional facial embeddings for high-accuracy authorization[cite: 1].
* **Feature-Based Behavior Analysis:** Overcoming the limitations of aerial camera motion, the system utilizes feature-based recognition to identify hidden or masked faces, prioritizing deep feature extraction over simple movement speed heuristics.
* **3D Visual Servoing (P-Controller):** Dynamic target tracking in 3D space, calculating autonomous Yaw rotation, Forward/Backward approach, and Altitude Hold to maintain a safe distance from the suspect.
* **Failsafe & Mission Interruption:** The AI and flight control subsystems are decoupled. The operator can toggle Offboard mode via RC; upon deactivation, the UAV safely halts in Position mode.
* **Real-Time Cloud Alerts:** Instantaneous Firestore updates and image uploads trigger alerts on a custom mobile application.

## 🏗️ System Architecture

The architecture relies on asynchronous communication between the perception unit (Jetson Nano), the flight controller (Pixhawk), and the cloud (Firebase).

<!-- GÖRSEL 3: BURAYA SİSTEM MİMARİSİ BLOK ŞEMASINI EKLE -->
![System Architecture Diagram](media/system_diagram.png)

## 🛠️ Hardware Specification

| Component | Specification |
| :--- | :--- |
| **UAV Frame** | Holybro X500 V2 quadcopter platform |
| **Flight Controller** | Pixhawk 6C (PX4 firmware) |
| **Edge Compute** | NVIDIA Jetson Nano Developer Kit |
| **Telemetry / Comm** | UART (`ttyTHS1`) at 115200 baud |
| **Battery** | Profuse 8000 mAh 65C 4S LiPo |
| **Ground Control** | QGroundControl |
| **RC Transmitter** | Configured with dedicated Offboard/Mission toggle (CH8) |

## 🧠 DeepStream and MAVSDK Pipeline

The deployment workflow targets the NVIDIA Jetson Nano, optimizing video processing through hardware acceleration while maintaining a strict 20Hz async flight control loop.

* **Inference:** GStreamer pipeline captures the feed, passing it through TensorRT optimized engines for human/face detection.
* **Visual Servoing:** Bounding box coordinates are translated into spatial errors (X-axis for Yaw, Y-axis for Altitude, Z-axis for Distance).
* **Flight Control:** MAVSDK asynchronously calculates velocity setpoints (`VelocityBodyYawspeed`) using tuned P-Gains. Safe altitude limits (min 3.0m) are hardcoded into the pipeline.
* **Cloud Sync:** A background thread uploads annotated frames to Firebase without blocking the 20Hz flight loop.

## 📊 Field Results & Performance

The system was rigorously validated in real-world outdoor scenarios:
* **Inference Speed:** Maintained an average processing time of 145 ms (approximately 7 FPS) on the Jetson Nano[cite: 1].
* **Detection Accuracy:** Achieved an 88% combined accuracy rate for human detection and face verification during dynamic flight[cite: 1].
* **System Latency:** Recorded an average end-to-end latency of just 0.8 seconds from the moment of detection to the FCM push notification on the mobile client[cite: 1].
* **Reliability:** Successfully kept the false positive rate at 8%, demonstrating strong resilience to outdoor lighting variations[cite: 1].

## 📂 Repository Structure

```text
holo-patrol-drone/
│
├── docs/
│   ├── system_architecture.md
│   ├── behavior_analysis.md
│   ├── hardware_setup.md
│   └── mobile_integration.md
│
├── media/
│   ├── flight_demo.gif
│   ├── cover_photo.jpg
│   └── system_diagram.png
│
├── src/
│   ├── trace_3d_tracker.py       # Core MAVSDK & DeepStream logic (Sample)
│   └── firebase_config.json      # Template for cloud integration
│
├── LICENSE
└── README.md
```
🔮 Limitations & Future Work
Power Management: Continuous Edge AI inference combined with Wi-Fi cloud syncing causes significant voltage sags on the Jetson Nano. Dedicated BECs are highly recommended.

Night Operations: The current model is trained on RGB data; thermal/LWIR camera integration is planned for future iterations.

Swarm Capabilities: Expanding the Firebase architecture to support multi-drone synchronization and shared geofenced zones.

📜 Citation
If you reference this architecture or project, please cite:
```text
@thesis{holo_patrol_2026,
  title      = {Autonomous Security Patrol Drone capable of Intrusion Detection with Face Recognition},
  author     = {Kesgin, Melih Can and Karaca, Mehmet Ali and Küçükkayalar, Doğa and Ayaz, Ecem Dilan},
  year       = {2026},
  school     = {Başkent University, Faculty of Engineering},
  type       = {Bachelor's Thesis},
  department = {Computer Engineering}
}
```
⚖️ License
This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0). See the LICENSE file for details.
