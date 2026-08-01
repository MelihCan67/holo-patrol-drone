# 🚁 HOLO-PATROL: Autonomous Security Patrol Drone

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![NVIDIA DeepStream](https://img.shields.io/badge/NVIDIA-DeepStream-76B900.svg)](https://developer.nvidia.com/deepstream-sdk)
[![MAVSDK](https://img.shields.io/badge/MAVSDK-Dronecode-1E4E8C.svg)](https://mavsdk.mavlink.io/)
[![Firebase](https://img.shields.io/badge/Firebase-Cloud-FFCA28.svg)](https://firebase.google.com/)
[![Tests](https://img.shields.io/github/actions/workflow/status/MelihCan67/holo-patrol-drone/tests.yml?branch=main&label=tests)](.github/workflows/tests.yml)
[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](LICENSE)

**3D Visual Servoing · Face Recognition (reference pipeline) · Jetson Nano · MAVSDK · Firebase Mobile Integration**

Bachelor's thesis project — Başkent University, Department of Computer Engineering, 2026
**Authors:** Melih Can Kesgin, Mehmet Ali Karaca, Doğa Küçükkayalar, Ecem Dilan Ayaz
**Advisor:** Asst. Prof. Dr. İclal Çetin Taş
**Supported by:** TürkTrust

*[Holo-Patrol Drone on the Field — media not included in this distribution]*

## 📑 Table of Contents

- [Field Validation & Demo](#-field-validation--demo)
- [Motivation & Overview](#-motivation--overview)
- [Operational Workflow](#-operational-workflow)
- [Key Highlights](#-key-highlights)
- [System Architecture](#️-system-architecture)
- [Hardware Specification](#️-hardware-specification)
- [DeepStream and MAVSDK Pipeline](#-deepstream-and-mavsdk-pipeline)
- [Field Results & Performance](#-field-results--performance)
- [AI Transparency & Documentation](#-ai-transparency--documentation)
- [Repository Structure](#-repository-structure)
- [Quick Start (Onboard Deployment)](#-quick-start-onboard-deployment)
- [Testing & Continuous Integration](#-testing--continuous-integration)
- [Model Deployment (TensorRT Export)](#️-model-deployment-tensorrt-export)
- [Limitations & Future Work](#-limitations--future-work)
- [Citation](#-citation)
- [License](#️-license)

## 📺 Field Validation & Demo

*[3D Visual Servoing and Target Lock — media not included in this distribution]*

## 🚀 Motivation & Overview

Traditional security systems rely heavily on static camera networks or manual drone patrols, which are susceptible to human error and response delays. **HOLO-PATROL** was engineered to bridge this gap by introducing an operator-authorized autonomous aerial security solution — the drone patrols and tracks targets in 3D space on its own once the operator authorizes Offboard mode — aligned with the UN Sustainable Development Goal 9 (Industry, Innovation and Infrastructure).

This repository presents an end-to-end autonomous UAV security ecosystem. Before any physical deployment, the event flow was rigorously de-risked using a Gazebo / PX4 SITL simulation. Operating on a Holybro X500 V2 frame, the system uses an NVIDIA Jetson Nano as a companion computer to process aerial video. When an unauthorized entry is detected during a routine patrol mission — in the target design, refined by face recognition once fully integrated (see Capability status below); today, the public flight scripts trigger on person detection alone — and the operator authorizes Offboard mode via the RC switch, the AI subsystem takes over velocity control via MAVSDK to autonomously track the target in 3D space. Simultaneously, high-resolution evidence is transmitted to a custom mobile application via Firebase.

## 🎯 Operational Workflow

The system operates in a decoupled, multi-stage workflow:
1. **Routine Patrol:** The UAV executes a predefined GPS-based geofenced patrol via QGroundControl (Mission Mode), sustaining operations for approximately 15-20 minutes per mission.
2. **Threat Detection:** The onboard Jetson Nano continuously runs YOLOv8 and facial recognition pipelines on the live camera feed.
3. **AI-Assisted Target Lock:** Upon detecting a threat, the operator authorizes Offboard mode via the RC switch; the Jetson then takes over velocity control over UART and tracks the target dynamically using 3D Visual Servoing.
4. **Cloud Alert:** An evidence frame and alert metadata (target ID, detection confidence, timestamp, severity) are pushed to Firebase Firestore/Cloud Storage, which the mobile app uses to surface a notification. The current payload does not include GPS position, altitude, or velocity.
5. **Resume Patrol:** Once the threat is cleared or the operator toggles the RC switch, the drone safely halts and awaits the command to resume its original geofenced route.

## 🌟 Key Highlights

* **Full UAV Hardware & AI Integration:** Holybro X500 V2 UAV platform synchronized with a Pixhawk 6C flight controller and Jetson Nano.
* **Advanced Face Verification (reference pipeline):** Utilizes a Dlib HOG-based face detector paired with FaceNet to extract 128-dimensional facial embeddings for high-accuracy authorization. Implemented and validated as a standalone module — see the capability table below for its integration status.
* **Feature-Based Behavior Analysis (reference pipeline):** Overcoming the limitations of aerial camera motion, the behavior state machine uses feature-based recognition to identify hidden or masked faces, prioritizing deep feature extraction over simple movement speed heuristics.
* **3D Visual Servoing (P-Controller):** Dynamic target tracking in 3D space, calculating autonomous Yaw rotation, Forward/Backward approach, and Altitude Hold to maintain a safe distance from the suspect. A hard 3-meter altitude floor reliably blocks further AI-commanded descent for enhanced safety.
* **Failsafe & Mission Interruption:** The AI and flight control subsystems are decoupled. The operator can toggle Offboard mode via RC; upon deactivation, the UAV safely halts in Position mode.
* **Real-Time Cloud Alerts:** Instantaneous Firestore updates and image uploads trigger alerts on a custom mobile application. Alert uploads run in a background thread so that network activity never blocks the flight-control loop.
* **Testable, Modular Core:** The control law, target selection, behavior-state machine, and alert logic are refactored into a hardware-independent `src/holo_patrol` package, covered by an automated `pytest` suite that runs on every push via GitHub Actions.
* **AI Transparency by Design:** The project ships a [`MODEL_CARD.md`](MODEL_CARD.md) and [`DATA_CARD.md`](DATA_CARD.md) documenting model performance, known limitations, dataset composition, and privacy/ethics considerations — not just code.

### Capability status

The face-verification and behavior-analysis components are implemented and unit-tested, but the public real-flight scripts (`yaw_tracker.py`, `visual_tracker_3d.py`) currently only wire up person detection and visual-servo tracking. Face-triggered flight decisions are not yet integrated into the public flight path:

| Capability | Status |
| :--- | :--- |
| Person detection | Implemented and field-tested |
| Yaw tracking | Implemented and field-tested |
| Three-axis visual servoing | Implemented and field-tested |
| Firebase evidence upload | Implemented |
| Face verification (Dlib + FaceNet) | Implemented; validated separately from the flight scripts |
| Behavior state machine (`behavior.py`) | Unit-tested reference implementation |
| Face-triggered flight decision | Not integrated into the public flight scripts |

## 🏗️ System Architecture

The architecture relies on asynchronous communication between the perception unit (Jetson Nano), the flight controller (Pixhawk), and the cloud (Firebase). See [`docs/system_architecture.md`](docs/system_architecture.md) for the full layered breakdown and data-flow timing table.

*[System Architecture Diagram — media not included in this distribution]*

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

Full wiring diagrams and power-distribution notes: [`docs/hardware_setup.md`](docs/hardware_setup.md).

## 🧠 DeepStream and MAVSDK Pipeline

The deployment workflow targets the NVIDIA Jetson Nano, optimizing video processing through hardware acceleration while maintaining a strict 20Hz async flight control loop.

* **Capture:** The Sony IMX477 camera captures frames at 60 FPS via the CSI interface.
* **Inference:** GStreamer pipeline passes the feed through TensorRT-optimized engines for human/face detection. See [`scripts/export_tensorrt.py`](scripts/export_tensorrt.py) for the `.pt → .engine` export step required before deployment.
* **Visual Servoing:** Bounding box coordinates are translated into spatial errors (X-axis for Yaw, Y-axis for Altitude, Z-axis for Distance). Full control-law derivation: [`docs/visual_servoing.md`](docs/visual_servoing.md).
* **Flight Control:** MAVSDK asynchronously calculates velocity setpoints (`VelocityBodyYawspeed`) using tuned P-Gains. Safe altitude limits (min 3.0 m) are hardcoded into the pipeline.
* **Cloud Sync:** A background thread uploads annotated frames to Firebase without blocking the 20 Hz flight loop.

## 📊 Field Results & Performance

The system was evaluated during a limited set of real-world outdoor flight trials:
* **Inference Speed:** Maintained an average processing time of ~69 ms (approximately 14.5 FPS) on the Jetson Nano.
* **Detection Accuracy:** Achieved an 88% combined accuracy rate for human detection and face verification during dynamic flight.
* **System Latency:** Recorded an average end-to-end latency of just 0.8 seconds from the moment of detection to the FCM push notification on the mobile client. (FCM delivery itself is handled by the mobile app / a Cloud Function listening on Firestore, not by the Python scripts in this repository.)
* **Reliability:** Successfully kept the false positive rate at 8%, demonstrating strong resilience to outdoor lighting variations.

Detector architecture selection, baseline comparisons (SSD, Faster R-CNN, RetinaNet, CenterNet, YOLOv8n), and dataset details live in [`MODEL_CARD.md`](MODEL_CARD.md) and [`DATA_CARD.md`](DATA_CARD.md).

## 📇 AI Transparency & Documentation

| Document | Purpose |
| :--- | :--- |
| [`MODEL_CARD.md`](MODEL_CARD.md) | Model details, intended use, evaluation metrics, ethical considerations, and caveats for both the YOLOv8n detector and the Dlib+FaceNet verification pipeline. |
| [`DATA_CARD.md`](DATA_CARD.md) | Composition, collection process, and privacy handling for the VisDrone benchmark and the local (non-distributed) authorized-personnel face database. |
| [`docs/system_architecture.md`](docs/system_architecture.md) | Layered architecture and end-to-end data-flow timing. |
| [`docs/behavior_analysis.md`](docs/behavior_analysis.md) | Detector architecture evaluation and the Feature-Based Behavior Analysis state machine. |
| [`docs/visual_servoing.md`](docs/visual_servoing.md) | Full P-controller derivation for yaw, distance, and vertical regulation. |
| [`docs/hardware_setup.md`](docs/hardware_setup.md) | Physical wiring, power distribution, and vibration-dampening notes. |
| [`docs/software_setup.md`](docs/software_setup.md) | Onboard software stack, runtime assets, and pre-deployment checklist. |
| [`docs/quick_start.md`](docs/quick_start.md) | Progressive real-flight validation sequence (yaw-only → full 3D tracking). |

## 📂 Repository Structure

```text
holo-patrol-drone/
│
├── docs/
│   ├── system_architecture.md        # Layered architecture overview
│   ├── behavior_analysis.md          # State machine and verification
│   ├── hardware_setup.md             # Physical wiring and configurations
│   ├── software_setup.md             # Target environment and dependencies
│   ├── visual_servoing.md            # P-Controller and tracking logic
│   └── quick_start.md                # Progressive real-flight test guide
│
├── config/
│   └── firebase.example.json         # Template for cloud integration (never commit real keys)
│
├── src/
│   ├── yaw_tracker.py                 # Stage 1: onboard yaw-only controller
│   ├── visual_tracker_3d.py           # Stage 2: onboard full 3D visual servoing
│   ├── gazebo_sitl_tracker.py         # Gazebo / PX4 SITL simulation prototype
│   │
│   └── holo_patrol/                  # Hardware-independent, unit-tested core
│       ├── perception/
│       │   ├── detection.py          # Target selection (highest-confidence policy)
│       │   └── behavior.py           # PERSON / FACE NOT VISIBLE / MASK SUSPECT state machine
│       ├── flight_control/
│       │   ├── visual_servo.py       # Pure P-controller math (yaw, distance, altitude)
│       │   └── offboard_guard.py     # Flight-mode authorization gating
│       └── cloud/
│           └── alerts.py             # Alert cooldown throttle + Firestore payload shaping
│
├── scripts/
│   └── export_tensorrt.py            # YOLOv8 .pt → TensorRT .engine export for the Jetson Nano
│
├── tests/                            # pytest unit tests for src/holo_patrol (runs in CI)
│   ├── test_visual_servo.py
│   ├── test_perception.py
│   ├── test_behavior_state.py
│   ├── test_alerts.py
│   └── test_offboard_guard.py
│
├── .github/
│   └── workflows/
│       └── tests.yml                 # CI: ruff lint + pytest on every push/PR
│
├── MODEL_CARD.md                     # AI transparency: model details, metrics, ethics
├── DATA_CARD.md                      # Dataset documentation (VisDrone + local face DB)
├── CITATION.cff                      # Machine-readable citation (GitHub "Cite this repository")
├── pyproject.toml                    # Package metadata, pytest & ruff configuration
├── requirements-dev.txt              # Dependencies for linting/testing the core package
├── LICENSE
└── README.md
```

## 🚀 Quick Start (Onboard Deployment)

After verifying the camera stream and MAVLink connection over `/dev/ttyTHS1`, you can initiate the autonomous tracking node. Ensure a compatible RTP/H.264 receiver is listening on UDP port 5000.

```bash
# Run the full 3D tracking script and stream video to the Ground Station IP
python3 src/visual_tracker_3d.py <GROUND_STATION_IP>
```

> The script waits for the operator to switch the vehicle into `OFFBOARD` mode via the configured RC switch before it starts issuing any autonomous commands.

For the recommended progressive validation order — Gazebo/SITL, then a yaw-only flight test, then full 3D tracking — see [`docs/quick_start.md`](docs/quick_start.md).

## 🧪 Testing & Continuous Integration

The refactored core in `src/holo_patrol/` (control law, target selection, behavior classification, and alert throttling) has no dependency on MAVSDK, DeepStream, or Firebase, so it is fully unit-tested and runs in CI without any drone or Jetson hardware attached.

```bash
pip install -r requirements-dev.txt
pip install -e .
pytest tests/ -v
ruff check src tests
```

Every push and pull request to `main` triggers [`.github/workflows/tests.yml`](.github/workflows/tests.yml), which lints the codebase with `ruff` and runs the full `pytest` suite across multiple Python versions. The monolithic onboard scripts (`yaw_tracker.py`, `visual_tracker_3d.py`, `gazebo_sitl_tracker.py`) require physical or simulated flight hardware and are instead validated through the manual field sequence in [`docs/quick_start.md`](docs/quick_start.md).

## ⚙️ Model Deployment (TensorRT Export)

Standard PyTorch (`.pt`) inference is too slow for the onboard DeepStream pipeline's sub-200 ms/frame budget. Before deploying a trained YOLOv8 model to the Jetson Nano, export it to a TensorRT engine:

```bash
python3 scripts/export_tensorrt.py \
    --weights weights/yolov8n_holo_patrol.pt \
    --imgsz 640 \
    --half \
    --workspace 4 \
    --device 0 \
    --output engines/
```

Then point `model-engine-file` in `config_infer_primary_yoloV8.txt` at the generated `.engine` file. See [`docs/software_setup.md`](docs/software_setup.md) for the full onboard configuration checklist.

## 🔮 Limitations & Future Work

**Power Management:** Continuous Edge AI inference combined with Wi-Fi cloud syncing causes significant voltage sags on the Jetson Nano. Dedicated BECs are highly recommended.

**Night Operations:** The current model is trained on RGB data; thermal/LWIR camera integration is planned for future iterations.

**Swarm Capabilities:** Expanding the Firebase architecture to support multi-drone synchronization and shared geofenced zones.

**Fairness Evaluation:** No formal demographic fairness audit has been conducted on the face-verification stage — see the Ethical Considerations section of [`MODEL_CARD.md`](MODEL_CARD.md).

## 📜 Citation

If you reference this architecture or project, please cite it using the metadata in [`CITATION.cff`](CITATION.cff) (GitHub's "Cite this repository" button generates APA/BibTeX automatically from this file), or manually:

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

## ⚖️ License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0). See the [`LICENSE`](LICENSE) file for details.