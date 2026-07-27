"""
holo_patrol.flight_control.visual_servo
========================================
Pure, hardware-independent implementation of HOLO-PATROL's image-based
visual servoing control law, as documented in ``docs/visual_servoing.md``.

This module has **no dependency on MAVSDK, GStreamer, or DeepStream**
so the control law itself — dead zones, proportional gains, velocity
clamping, and the minimum-altitude safety rule — can be unit-tested on
any machine (including a CI runner) without a Jetson Nano, a Pixhawk,
or a camera attached.

The default parameter values below are copied exactly from the
onboard scripts:

- Yaw parameters match both ``test_yaw.py`` and ``test_3d_tracker.py``.
- Forward/vertical parameters and the altitude floor match
  ``test_3d_tracker.py`` specifically (``test_yaw.py`` never computes
  or sends non-zero forward/down commands — see
  ``VisualServoController(enable_translation=False)`` below).
"""
from dataclasses import dataclass


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(min(value, upper), lower)


@dataclass(frozen=True)
class VisualServoConfig:
    """Tunable control-law parameters.

    Defaults match ``test_3d_tracker.py`` exactly (see
    ``docs/visual_servoing.md``, Sections 4 and 5). Construct a custom
    ``VisualServoConfig`` to reproduce the Gazebo prototype's
    (``main.py``) different gains and limits if needed for comparison
    or simulation work.
    """
    image_width: int = 1280
    image_height: int = 720

    # Yaw regulation
    yaw_dead_zone_px: float = 40.0
    yaw_gain: float = 0.035
    yaw_rate_limit_deg_s: float = 30.0

    # Following-distance regulation (forward/backward)
    target_box_height_px: float = 300.0
    distance_dead_zone_px: float = 30.0
    forward_gain: float = 0.018
    forward_limit_m_s: float = 1.5
    backward_limit_m_s: float = -1.0

    # Vertical regulation
    vertical_dead_zone_px: float = 35.0
    vertical_gain: float = 0.008
    vertical_limit_m_s: float = 0.5

    # Safety
    min_safe_altitude_m: float = 3.0

    @property
    def image_center_x(self) -> float:
        return self.image_width / 2

    @property
    def image_center_y(self) -> float:
        return self.image_height / 2


@dataclass(frozen=True)
class VelocitySetpoint:
    """Mirrors MAVSDK's ``VelocityBodyYawspeed(forward, right, down, yaw_rate)``.

    ``right`` is always ``0.0`` in this project — lateral translation
    is not used (see docs/visual_servoing.md, Section 3).
    """
    forward: float = 0.0
    right: float = 0.0
    down: float = 0.0
    yaw_rate: float = 0.0


class VisualServoController:
    """Implements the control law from docs/visual_servoing.md.

    Set ``enable_translation=False`` to reproduce ``test_yaw.py``'s
    behavior exactly: yaw is computed and commanded, while forward and
    down are always forced to zero. Leave it ``True`` (default) to
    reproduce ``test_3d_tracker.py``.
    """

    def __init__(self, config: VisualServoConfig = None, enable_translation: bool = True):
        self.config = config or VisualServoConfig()
        self.enable_translation = enable_translation

    def compute_yaw_rate(self, target_center_x: float) -> float:
        c = self.config
        error_x = target_center_x - c.image_center_x
        if abs(error_x) < c.yaw_dead_zone_px:
            return 0.0
        return _clamp(error_x * c.yaw_gain, -c.yaw_rate_limit_deg_s, c.yaw_rate_limit_deg_s)

    def compute_forward_speed(self, target_box_height: float) -> float:
        c = self.config
        error_distance = c.target_box_height_px - target_box_height
        if abs(error_distance) < c.distance_dead_zone_px:
            return 0.0
        return _clamp(error_distance * c.forward_gain, c.backward_limit_m_s, c.forward_limit_m_s)

    def compute_down_speed(self, target_center_y: float) -> float:
        c = self.config
        error_y = target_center_y - c.image_center_y
        if abs(error_y) < c.vertical_dead_zone_px:
            return 0.0
        return _clamp(error_y * c.vertical_gain, -c.vertical_limit_m_s, c.vertical_limit_m_s)

    def apply_altitude_protection(self, down_speed: float, relative_altitude_m: float) -> float:
        """Blocks further AI-commanded descent once the safety floor is
        reached, per docs/visual_servoing.md Section 5.4. Climb
        (negative ``down_speed``) is never blocked by this rule.
        """
        if relative_altitude_m <= self.config.min_safe_altitude_m and down_speed > 0:
            return 0.0
        return down_speed

    def compute_setpoint(
        self,
        target_center_x: float,
        target_center_y: float,
        target_box_height: float,
        relative_altitude_m: float,
    ) -> VelocitySetpoint:
        """Compute the full setpoint for a currently-tracked target."""
        yaw_rate = self.compute_yaw_rate(target_center_x)

        if not self.enable_translation:
            return VelocitySetpoint(forward=0.0, right=0.0, down=0.0, yaw_rate=yaw_rate)

        forward = self.compute_forward_speed(target_box_height)
        down = self.compute_down_speed(target_center_y)
        down = self.apply_altitude_protection(down, relative_altitude_m)
        return VelocitySetpoint(forward=forward, right=0.0, down=down, yaw_rate=yaw_rate)

    @staticmethod
    def zero_setpoint() -> VelocitySetpoint:
        """Setpoint to send when no target is detected, or Offboard is
        not authorized — see docs/visual_servoing.md, Section 6.
        """
        return VelocitySetpoint()
