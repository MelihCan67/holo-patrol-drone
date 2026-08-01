"""
holo_patrol.perception.target_state
====================================
Atomic snapshot of "the current best target", shared between the
DeepStream probe thread (``osd_sink_pad_buffer_probe``, running on
GStreamer/GLib's own thread) and the asyncio MAVSDK control loop in
``yaw_tracker.py`` and ``visual_tracker_3d.py``.

Both scripts previously bridged these two threads with five separate
global variables (``global_target_center_x``, ``global_target_center_y``,
``global_target_height``, ``global_track_id``, ``global_target_detected``
plus a ``last_detection_time`` timestamp), each written and read without
a lock. CPython's GIL makes any *single* variable's read/write atomic,
but it does not make *reading all five together* atomic: the control
loop could read ``center_x`` from one probe callback and ``height``
from the next, briefly acting on an internally-inconsistent target.
``TARGET_TIMEOUT_S`` freshness checks made this narrow window low-risk
in practice, but not impossible.

``TargetState`` collapses all of that into one immutable object. The
probe thread builds a brand-new ``TargetState`` each frame and does one
reference assignment (``global_target_state = TargetState(...)``) --
a single reference assignment to a name is atomic in CPython, so the
control loop always reads one complete, self-consistent snapshot
without needing a ``threading.Lock``.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetState:
    """An atomic, self-consistent snapshot of the current best target.

    ``detected_at`` is a ``time.time()``-style timestamp recorded when
    this snapshot was produced; combine it with ``is_fresh`` to decide
    whether the control loop should still act on it.
    """
    detected: bool = False
    center_x: float = 0.0
    center_y: float = 0.0
    height: float = 0.0
    track_id: int = -1
    detected_at: float = float("-inf")

    def is_fresh(self, now: float, timeout_s: float) -> bool:
        """Whether this snapshot is recent enough for the control loop to
        act on, per the ``TARGET_TIMEOUT_S`` freshness window documented
        in both onboard scripts.
        """
        return self.detected and (now - self.detected_at) < timeout_s

    @staticmethod
    def none() -> "TargetState":
        """The state to hold when no target is currently detected."""
        return TargetState()
