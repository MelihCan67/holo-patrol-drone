# 🧠 Behavior Analysis & Edge AI Pipeline

The core intelligence of the HOLO-PATROL system resides in its decoupled Edge AI pipeline, running exclusively on the NVIDIA Jetson Nano. This document outlines the object detection evaluation, behavior analysis, and facial verification mechanisms utilized during autonomous patrol missions. Our fundamental operational constraint is to maintain a detection budget of under 200 ms per frame to ensure real-time responsiveness.

## 1. Object and Human Detection: Architecture Evaluation

Deploying object detection models on unmanned aerial vehicles (UAVs) introduces distinct challenges. Aerial datasets, such as VisDrone, are characterized by extreme scale variations, dense packing of targets, and significant background clutter, causing objects to appear extremely small and reducing the effectiveness of feature extraction.

To select the most viable model, we conducted a two-stage evaluation. Baseline evaluations were first performed on a high-performance workstation (Intel Core i7-11800H, 16 GB DDR4 RAM, NVIDIA GeForce RTX 3060 Laptop GPU) to establish a theoretical ceiling, before deploying the optimal candidate to the resource-constrained Jetson Nano.

### Baseline Comparison Highlights
*   **SSD (MobileNet Backbone):** Achieved the highest workstation inference speed (up to 92.50 FPS) but failed in accuracy, particularly for small or partially obscured individuals (mAP50 dropped to 0.184 on the VisDrone dataset).
*   **Faster R-CNN (ResNet-50/101):** Delivered the highest detection accuracy by a significant margin (mAP50 0.512 on VisDrone) due to its two-stage region proposal architecture. However, inference speeds capped at 7-15 FPS on a powerful GPU, making it fundamentally too slow for our real-time aerial requirements.
*   **RetinaNet & CenterNet:** RetinaNet successfully addressed class imbalance using the Focal Loss function, and CenterNet offered an efficient anchor-free structure. Yet, both hovered in the 15-38 FPS range on the workstation, falling short of the sub-second reaction requirement.
*   **YOLOv8n (Selected):** YOLOv8 abandons anchor boxes in favor of an anchorless detection strategy that directly estimates object centers. It achieved an optimal balance with ~71 FPS and a respectable mAP50 of 0.4736 on the VisDrone dataset during baseline tests. Furthermore, its exceptionally small model size (approximately 6 MB) ensures a minimal memory footprint, which is critical for edge deployment and battery preservation.

### Real-Time Edge Deployment
Following the baseline selection, YOLOv8n was deployed directly onto the NVIDIA Jetson Nano integrated into the UAV. During actual autonomous drone flights, the model successfully executed real-time object detection on the live camera feed, maintaining an average inference speed of **14.50 FPS**.

## 2. Feature-Based Behavior Analysis

Relying solely on movement speed for behavior analysis from a moving UAV is highly prone to false positives due to camera motion, vibrations, and gimbal adjustments. To resolve this, HOLO-PATROL implements a **Feature-Based Behavior Analysis** state machine. 

Instead of speed, the system analyzes specific visual characteristics and tracks them over a temporal window to classify threats:

| State Tag | Condition | System Action |
| :--- | :--- | :--- |
| **`PERSON`** | Face detected and recognized via the whitelist. | Routine log generated; no alarm triggered; patrol continues. |
| **`FACE NOT VISIBLE`** | Human detected, but facial features are obscured or turned away. | Target cached in temporal memory; system flags for continuous tracking without immediate critical alarm. |
| **`MASK SUSPECT`** | Face is intentionally hidden (e.g., masks) or visibility threshold is unmet for a prolonged duration. | **Critical Alarm** triggered; UAV initiates autonomous Visual Servoing tracking; Firebase alert pushed. |

### Behavior State Examples

**1. Authorized Personnel (`PERSON`)**
The system successfully detects the face, runs the verification pipeline, and matches the embedding with an authorized identity. No alarm is triggered.
*[Face Recognized - Person — media not included in this distribution]*

**2. Obscured Face (`FACE NOT VISIBLE`)**
A human is detected, but the facial features are not visible (e.g., turned away). The system caches the target ID and continues monitoring.
*[Face Not Visible — media not included in this distribution]*

**3. Suspicious Activity (`MASK SUSPECT`)**
The target is intentionally obscuring their face with a mask. The system escalates the event, triggering a critical alarm and initiating autonomous tracking.
*[Mask Suspect — media not included in this distribution]*

## 3. Two-Stage Face Verification & Privacy

When a human target is acquired, the system attempts to verify their authorization status using a lightweight, two-stage pipeline:
1. **Face Localization:** A Dlib HOG-based (Histogram of Oriented Gradients) detector rapidly isolates the face within the bounding box.
2. **Identity Verification:** The isolated face is passed through **FaceNet**, which reframes face verification as a distance problem in an embedding space. It generates a 128-dimensional embedding vector that is compared against a local database of authorized personnel.

### Data Protection and KVKK Compliance
Privacy by design is a core principle of this project. The system does not retain any intermediate face images. Once the identity verification check is complete, the video frames and the generated embeddings are immediately and permanently deleted from memory and temporary storage to strictly comply with Turkey's KVKK (Personal Data Protection Law) regulations.