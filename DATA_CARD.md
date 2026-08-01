# 🗂️ Data Card — HOLO-PATROL

This data card follows the structure of Google's [Data Cards Playbook](https://sites.research.google/datacardsplaybook/). It documents the **two** distinct data sources involved in HOLO-PATROL: the public benchmark used to select the detector architecture, and the private, locally-managed dataset used for identity verification during operation. See [`MODEL_CARD.md`](MODEL_CARD.md) for how these datasets relate to model selection and evaluation.

---

## Dataset 1 — VisDrone (Detector Architecture Benchmark)

### Overview

| | |
|---|---|
| **Name** | VisDrone |
| **Role in this project** | Public benchmark used solely to compare candidate detector architectures (SSD, Faster R-CNN, RetinaNet, CenterNet, YOLOv8n) before committing to one for edge deployment |
| **Distributed with this repo?** | No — VisDrone is a third-party dataset; this repository does not redistribute it |
| **Access** | Publicly available; see the [official VisDrone project](http://aiskyeye.com/) for terms and download |

### Motivation

Off-the-shelf detectors are typically benchmarked on ground-level imagery (COCO, Pascal VOC), which does not reflect the extreme scale variation, small object size, dense packing, and background clutter characteristic of aerial security footage. VisDrone was chosen specifically because it captures these aerial-specific failure modes, making it a much closer proxy for HOLO-PATROL's actual operating conditions than a ground-level benchmark.

### Composition

VisDrone is a large-scale drone-captured benchmark containing dense pedestrian and vehicle annotations across varied altitudes, viewpoints, and environments. HOLO-PATROL's evaluation used it specifically to measure **mAP50 for the `person` class** across candidate architectures — see `docs/behavior_analysis.md`, Section 1, for the resulting comparison table.

### Collection Process

VisDrone was collected and released by its original authors/maintainers; this project did not participate in its collection and used it strictly as a pre-existing, published benchmark.

### Preprocessing / Use in This Project

- Used only for **baseline architecture comparison** on a workstation (Intel i7-11800H, RTX 3060 Laptop GPU) — not for the final onboard evaluation.
- No custom relabeling, filtering, or augmentation of VisDrone is described or distributed by this project.
- The onboard, real-flight accuracy figures reported in the README (88% combined accuracy, 8% false-positive rate) come from **live field flights**, not from VisDrone — VisDrone informed model *selection*, not final *deployment* metrics.

### Known Limitations

- VisDrone reflects its own collection conditions (specific regions, altitudes, camera hardware); performance on it is not a guarantee of equivalent performance on HOLO-PATROL's specific airframe, camera (Sony IMX477), or operating environment.
- As with most aerial datasets, small and heavily occluded targets are under-represented relative to their real-world detection difficulty, which likely means real-world small/occluded-target performance is somewhat lower than the reported mAP50 baseline suggests.

---

## Dataset 2 — Local Authorized-Personnel Face Database

### Overview

| | |
|---|---|
| **Name** | Local authorized-personnel embedding database (project-internal, not a published dataset) |
| **Role in this project** | Reference set of 128-dimensional FaceNet embeddings used to verify whether a detected face belongs to an authorized individual |
| **Distributed with this repo?** | **No.** This is private, personally identifiable data and is intentionally excluded from the public repository |
| **Access** | Not publicly available by design |

### Motivation

The behavior-analysis state machine (`docs/behavior_analysis.md`) needs a way to distinguish `PERSON` (recognized, authorized) from `MASK SUSPECT` (unrecognized / deliberately obscured). This requires a local reference set of authorized identities to compare against — this is that reference set.

### Composition

A small, operator-curated set of face embeddings (128-dimensional FaceNet vectors), one or more per authorized individual, generated from enrollment images captured specifically for this system. No demographic, age, or other metadata beyond the embedding-to-identity mapping is described as being stored.

### Collection Process

Enrollment images are provided directly by authorized personnel for the explicit purpose of inclusion in this whitelist (i.e., collected with the data subject's knowledge and for a stated security purpose), rather than scraped or sourced from an external dataset.

### Preprocessing / Pipeline

1. **Localization:** Dlib HOG detector isolates the face region from the enrollment (or live) image.
2. **Embedding:** FaceNet converts the localized face into a 128-dimensional vector.
3. **Storage:** Only the embedding vector — not the source image — is intended to persist in the local database, for authorized personnel.
4. **Runtime comparison:** Live detections are embedded the same way and compared by distance against the stored set; **the live frame and its generated embedding are deleted immediately after the comparison** (they are not added to the database).

### Uses

- **Intended use:** Real-time, on-device authorization check during active patrol missions, strictly within the geofenced operating area.
- **Out-of-scope use:** Any secondary use (e.g., building a general-purpose face recognition dataset, sharing embeddings outside this system, long-term identity tracking) is explicitly out of scope and not supported by this project's data-handling design.

### Distribution

**This dataset is never distributed.** It is excluded from version control (see `.gitignore` guidance in `docs/software_setup.md`) and must be provisioned locally by each operator/deployment. The public repository ships no real or synthetic identities, and no enrollment images.

### Privacy, Legal Basis, and Retention (KVKK Compliance)

> **Scope note:** the retention design below describes the face-verification
> reference pipeline (`src/holo_patrol/perception/behavior.py`) as
> specified in `docs/behavior_analysis.md`. As noted in the README's
> "Capability status" table, this pipeline is implemented and
> unit-tested but is **not yet wired into the public flight scripts**
> (`yaw_tracker.py`, `visual_tracker_3d.py`) — those scripts currently
> only run person detection, with no face processing at all. Until
> that integration lands, these retention guarantees describe the
> design target rather than the behavior of a currently-flying field
> deployment.

Per `docs/behavior_analysis.md`, Section 3:

- **Retention of live/query data:** none. Video frames and generated embeddings used for a live verification check are permanently deleted from memory and temporary storage immediately after the check completes.
- **Retention of enrollment data:** limited to the embedding vectors of enrolled, authorized personnel — required for the system's core authorization function.
- **Legal basis / compliance target:** Turkey's KVKK (Kişisel Verilerin Korunması Kanunu — Personal Data Protection Law). Deployments outside Turkey should independently confirm applicable local biometric-data regulations (e.g., GDPR, BIPA) before enrollment.
- **Data subject rights:** as the enrollment set is small and operator-managed, removal of an individual's embedding on request is expected to be a manual administrative action; this is not currently automated by the codebase in this repository.

### Known Limitations

- No formal fairness/bias evaluation has been performed on this local database or the FaceNet matching threshold (see the Ethical Considerations section of `MODEL_CARD.md`).
- Because the enrollment set is small and manually curated, verification accuracy is expected to degrade if the authorized-personnel list grows significantly beyond what a nearest-embedding lookup was evaluated against in this project.
- This dataset structure has not been evaluated for adversarial robustness (e.g., presentation/spoofing attacks against the face-verification stage).

---

## Maintenance

| | |
|---|---|
| **VisDrone** | Maintained externally by its original authors; this project has no update or maintenance role over it. |
| **Local face database** | Maintained per-deployment by the system operator; enrollment/removal is a manual, local administrative process, not a feature exposed by the current codebase. |

For questions about this data card, open a GitHub issue on this repository.
