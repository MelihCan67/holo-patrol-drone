# 🛠️ Hardware Setup & Integration Guide

The HOLO-PATROL platform is engineered by integrating an open-source flight control architecture with an edge computing unit. This document details the physical components, wiring configurations, and power distribution systems used on the Holybro X500 V2 frame.

## 1. System Architecture & Component List

The physical setup is split into two independent domains: the **Flight-Control Subsystem** (handling core stabilization and navigation) and the **AI Perception Subsystem** (handling companion computing and streaming).

| Component | Model / Specification | Role in the System |
| :--- | :--- | :--- |
| **UAV Frame** | Holybro X500 V2 Quadcopter | Lightweight, carbon-fiber structural backbone. |
| **Flight Controller** | Pixhawk 6C + PX4 Firmware | Core attitude stabilization, motor control, and navigation. |
| **Edge Compute** | NVIDIA Jetson Nano 4GB Kit | Onboard processing unit for YOLOv8 and facial verification. |
| **Companion Board** | Waveshare Carrier Board | Expands connectivity and power input for the Jetson Nano. |
| **Camera Module** | Sony IMX477 RGB CSI Camera | Low-latency, high-resolution aerial video acquisition. |
| **GPS Module** | M10 GPS (ublox) | Multi-constellation high-accuracy positioning for geofencing. |
| **Telemetry / Comm** | UART (`ttyTHS1`) @ 115200 baud | Asynchronous serial communication link between Pixhawk and Jetson Nano. |
| **Power Regulation** | Dedicated 5A UBEC | Delivers stable voltage and current to the Jetson Nano companion computer. |
| **Battery** | Profuse 8000 mAh 65C 4S LiPo | Primary power source providing ~15-20 minutes of flight time. |

## 2. Onboard Wiring & Telemetry Link

To ensure modularity and prevent flight safety compromises, the AI subsystem is deliberately decoupled from direct flight authority. 

*   **UART Connection:** The NVIDIA Jetson Nano communicates with the Pixhawk 6C flight controller via a dedicated UART serial interface (`/dev/ttyTHS1`) operating at a baud rate of `115200`. This channel handles telemetry requests and transmits MAVLink velocity setpoints when Offboard mode is engaged.
*   **Camera Integration:** The Sony IMX477 camera module is connected directly to the Jetson Nano via a high-speed **CSI (Camera Serial Interface)** port. This hardware-level connection avoids USB bandwidth bottlenecks, ensuring real-time frame acquisition without dropping packets.

## 3. Power Management and Environmental Dampening

*   **Power Distribution:** Heavy edge AI inference combined with active processing can cause critical voltage sags. To protect the Jetson Nano from power fluctuations originating from the main LiPo battery and ESCs, a dedicated **5A UBEC** is integrated into the power line.
*   **Vibration Control (Jello Effect Prevention):** High-frequency vibrations from the brushless motors (Holybro 2216 KV920) can introduce motion blur and compromise YOLOv8 bounding-box accuracy. Anti-vibration dampening mounts are installed beneath the camera and companion computer assembly to isolate mechanical noise.