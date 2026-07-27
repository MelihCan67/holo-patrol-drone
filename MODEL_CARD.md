# 📇 Model Card — HOLO-PATROL

This model card follows the format popularized by Google's [Model Cards for Model Reporting](https://arxiv.org/abs/1810.03993) and adopted internally by Google, Meta, and NVIDIA. It documents **two** models composed together in the HOLO-PATROL pipeline: a person detector and a face-verification pipeline. For training/evaluation dataset details, see [`DATA_CARD.md`](DATA_CARD.md).

---

## Model Details

| | |
|---|---|
| **Project** | HOLO-PATROL — Autonomous Security Patrol Drone |
| **Developers** | Kesgin, M. C.; Karaca, M. A.; Küçükkayalar, D.; Ayaz, E. D.; Yencilek, S. |
| **Institution** | Başkent University, Department of Computer Engineering |
| **Model date** | 2026 (Bachelor's Thesis) |
| **Model type** | Composite pipeline: real-time object detector + face embedding verifier |
| **License** | CC BY-NC 4.0 (see `LICENSE`) |
| **Contact** | Open a GitHub issue on this repository |

### Model A — Person Detector

| | |
|---|---|
| Architecture | YOLOv8n (anchor-free, single-stage) |
| Framework | Ultralytics (baseline) → NVIDIA DeepStream + TensorRT (deployment) |
| Model size | ~6 MB |
| Input | RGB frame, `1280 × 720` (onboard) / `640 × 480` (Gazebo prototype) |
| Output | Bounding boxes, class ID, confidence, per DeepStream `nvinfer` |
| Precision (deployed) | TensorRT-optimized (FP16 recommended on Jetson Nano — see `scripts/export_tensorrt.py`) |

### Model B — Face Verification Pipeline

| | |
|---|---|
| Stage 1 — Localization | Dlib HOG (Histogram of Oriented Gradients) face detector |
| Stage 2 — Embedding | FaceNet, producing a 128-dimensional embedding vector |
| Matching | Euclidean/cosine distance against a local authorized-personnel embedding database |
| Output | Match / no-match against the whitelist, feeding the behavior state machine (`docs/behavior_analysis.md`) |

---

## Intended Use

**Primary intended use:** Real-time aerial detection of humans and verification of their identity against a locally stored authorization whitelist, during autonomous geofenced security patrols, as part of a bachelor's thesis research prototype.

**Primary intended users:** Researchers, students, and engineers studying UAV-based security systems, edge AI deployment, or visual servoing — not end users of a deployed commercial security product.

**Out-of-scope uses:**
- Any use as the sole or final decision-maker in actions with legal, safety-critical, or use-of-force consequences.
- Persistent identity surveillance, tracking, or profiling of individuals outside the scope of an authorized, geofenced security patrol.
- Deployment in jurisdictions where aerial facial recognition is restricted or requires permits/approvals not obtained by the operator.
- Any use on minors or in contexts requiring specialized consent frameworks.
- Production/commercial deployment without independent safety and privacy re-certification — this is a research/thesis-grade prototype, not a certified product.

---

## Factors

Factors observed to affect model behavior, based on baseline and field evaluation:

- **Altitude and viewing angle** — aerial viewpoints shrink apparent person size and change silhouette, which is the primary reason lightweight, anchor-free detectors (YOLOv8n) were selected over higher-latency two-stage detectors.
- **Scene density and clutter** — the VisDrone benchmark used for baseline evaluation is characterized by dense target packing and background clutter, both known to depress detection accuracy for all evaluated architectures.
- **Lighting variation** — outdoor field tests spanned varying natural lighting; this is the primary contributor to the reported 8% false positive rate.
- **Occlusion / face obstruction** — deliberately or incidentally obscured faces route the pipeline into the `FACE NOT VISIBLE` or `MASK SUSPECT` behavior states rather than a detection failure (see `docs/behavior_analysis.md`).
- **Camera motion / vibration** — addressed at the hardware level with anti-vibration mounts (see `docs/hardware_setup.md`) rather than in the model itself.

---

## Metrics

### Detector baseline comparison (workstation: i7-11800H, RTX 3060 Laptop GPU, VisDrone dataset)

| Model | Workstation FPS | mAP50 (VisDrone) | Verdict |
|---|---:|---:|---|
| SSD (MobileNet) | up to 92.50 | 0.184 | Too inaccurate for small/occluded targets |
| Faster R-CNN (ResNet-50/101) | 7–15 | 0.512 | Most accurate, but far too slow for real-time use |
| RetinaNet | 15–38 | — | Addressed class imbalance (Focal Loss), still below the FPS target |
| CenterNet | 15–38 | — | Efficient anchor-free design, still below the FPS target |
| **YOLOv8n (selected)** | **~71** | **0.4736** | Best accuracy/speed/size trade-off for edge deployment |

### Onboard, real-flight metrics (Jetson Nano)

| Metric | Value |
|---|---|
| Average onboard inference speed | 14.50 FPS (~69–145 ms/frame depending on measurement point) |
| Combined human-detection + face-verification accuracy | 88% |
| False positive rate (field) | 8% |
| End-to-end detection → mobile push-notification latency | ~0.8 s |
| Operational detection budget (target) | < 200 ms/frame |

These figures are drawn directly from `docs/behavior_analysis.md` and the project README; no additional held-out test set beyond the described field flights was used to produce them.

---

## Evaluation Data

- **Detector baseline:** the public **VisDrone** aerial-imagery benchmark, used only for architecture selection (Section 1 of `docs/behavior_analysis.md`). HOLO-PATROL was not fine-tuned end-to-end on VisDrone for final deployment; VisDrone served as a proxy benchmark to choose the detector family.
- **Onboard field metrics:** real outdoor flight sessions with the physical UAV, described qualitatively in the README's Field Results section. No fixed, versioned, publicly released evaluation set backs these onboard numbers — see `DATA_CARD.md` for details and limitations.

## Training Data

See [`DATA_CARD.md`](DATA_CARD.md) for full details on the VisDrone benchmark and the (private, non-distributed) local authorized-personnel face database used for identity verification.

---

## Ethical Considerations

- **Surveillance and consent.** This system performs face detection and identity verification from an aerial platform. It is designed for a bounded, geofenced, authorized-personnel-only use case (e.g., a research campus or private facility under the operator's control), not open-ended public surveillance.
- **Data minimization.** Per `docs/behavior_analysis.md`, no intermediate face images are retained. Frames and embeddings are deleted immediately after the verification check, in line with Turkey's KVKK (Personal Data Protection Law).
- **Bias and fairness.** No formal fairness audit (across skin tone, gender presentation, age, or headwear) has been conducted on the face-verification stage. FaceNet-based embedding models are known in the literature to exhibit demographic performance gaps; this has not been independently measured for this deployment and should be treated as an open risk.
- **Dual-use risk.** Any autonomous aerial system that can detect, follow, and visually lock onto a person carries dual-use risk if repurposed outside its intended authorized-security context. This repository intentionally omits trained model weights, full production flight code, and credentials (see `docs/software_setup.md`, Section 9: Documentation Scope) to reduce misuse surface.
- **Human override.** By design, the system never acts on face-verification results without the flight-control layer separately requiring explicit operator authorization (RC Offboard switch) before any autonomous motion — see `docs/visual_servoing.md`, Section 7.

## Caveats and Recommendations

- The 88% combined accuracy and 8% false-positive figures come from a limited set of field trials, not a large, statistically powered test campaign — treat them as indicative, not production-grade guarantees.
- Detection performance on very small, heavily occluded, or fast-moving targets remains a known weak point of all evaluated architectures on aerial imagery, including the selected YOLOv8n.
- The face-verification whitelist approach assumes a small, controlled population of authorized personnel; it was not designed or evaluated for large-scale (thousands of identities) identity databases.
- Night / low-light and thermal operation are explicitly **not** covered by the current RGB-only model — see the README's Limitations & Future Work section.
- This model composition should not be used as-is in any context with legal, safety, or rights implications without independent re-evaluation.
