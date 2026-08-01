"""
holo_patrol.flight_control.offboard_guard
==========================================
Tracks PX4 flight-mode state and gates autonomous authority, mirroring
the ``monitor_flight_mode`` background task used in ``yaw_tracker.py``
and ``visual_tracker_3d.py`` (see docs/visual_servoing.md, Section 7).

This module has no MAVSDK dependency: it operates on plain strings, so
it can be fed real ``str(flight_mode)`` values from a live MAVSDK
telemetry stream, or synthetic strings in a unit test.
"""
from dataclasses import dataclass
from typing import List

from .visual_servo import VelocitySetpoint

AUTONOMY_MODES = ("OFFBOARD", "GUIDED")


@dataclass
class OffboardGuard:
    """Mirrors the ``global_is_offboard`` flag used onboard.

    Autonomous velocity setpoints are only authorized while the
    current PX4 flight mode string contains ``OFFBOARD`` or
    ``GUIDED``. The moment the operator switches to any other mode,
    authorization is withdrawn — this is the project's primary human
    override mechanism.
    """
    is_offboard: bool = False

    def update_flight_mode(self, mode_str: str) -> bool:
        """Update internal state from a raw PX4 flight-mode string.

        Returns ``True`` if authorization state changed (granted or
        revoked) as a result of this update, ``False`` otherwise.
        """
        mode_upper = mode_str.upper()
        authorized = any(tag in mode_upper for tag in AUTONOMY_MODES)
        changed = authorized != self.is_offboard
        self.is_offboard = authorized
        return changed

    def is_authorized(self) -> bool:
        return self.is_offboard


def build_zero_setpoint_stream(count: int = 10) -> List[VelocitySetpoint]:
    """Returns ``count`` zero-velocity setpoints.

    Both real-flight scripts stream ten zero setpoints before calling
    ``drone.offboard.start()`` (the earlier Gazebo prototype,
    ``main.py``, used fifteen) to satisfy PX4's requirement that
    setpoints already be flowing before Offboard mode is engaged. See
    docs/visual_servoing.md, Section 7, and docs/visual_servoing.md,
    Section 8 for the Gazebo-vs-real-flight comparison.
    """
    return [VelocitySetpoint() for _ in range(count)]
