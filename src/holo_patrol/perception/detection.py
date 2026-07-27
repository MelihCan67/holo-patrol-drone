"""
holo_patrol.perception.detection
=================================
Hardware-independent representation of a single object detection, plus
the target-selection policy used by the onboard controllers.

This mirrors the per-frame selection loop found inside the DeepStream
probe callbacks (`osd_sink_pad_buffer_probe`) in both `test_yaw.py`
and `test_3d_tracker.py`: among all detections of the target class
(person, class ID 0), pick the single highest-confidence one for the
current frame. It intentionally has no dependency on `pyds` or
GStreamer, so a DeepStream probe (or a unit test) can construct plain
`Detection` objects and reuse this exact selection policy.
"""
from dataclasses import dataclass
from typing import Iterable, Optional

PERSON_CLASS_ID = 0


@dataclass(frozen=True)
class Detection:
    """A single object detection in image-pixel coordinates.

    Coordinates follow the same convention used onboard: `x1, y1` is
    the top-left corner and `x2, y2` is the bottom-right corner of the
    bounding box.
    """
    class_id: int
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    track_id: int = -1

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def width(self) -> float:
        return self.x2 - self.x1


class TargetSelector:
    """Selects the single best target from a frame's detections.

    Matches the onboard logic exactly: among detections whose
    `class_id` equals `target_class_id`, return the one with the
    highest `confidence`. Returns ``None`` if no matching detection is
    present in the frame — the caller is then expected to send a
    zero-velocity setpoint (see ``flight_control.visual_servo``).
    """

    def __init__(self, target_class_id: int = PERSON_CLASS_ID):
        self.target_class_id = target_class_id

    def select(self, detections: Iterable[Detection]) -> Optional[Detection]:
        best: Optional[Detection] = None
        for det in detections:
            if det.class_id != self.target_class_id:
                continue
            if best is None or det.confidence > best.confidence:
                best = det
        return best
