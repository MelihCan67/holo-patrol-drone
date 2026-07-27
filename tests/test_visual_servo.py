import pytest

from holo_patrol.flight_control.visual_servo import (
    VelocitySetpoint,
    VisualServoConfig,
    VisualServoController,
)


def test_yaw_within_dead_zone_is_zero():
    controller = VisualServoController()
    # image_center_x = 640; target at 650 -> error_x = 10 px, inside the 40 px dead zone
    assert controller.compute_yaw_rate(target_center_x=650) == 0.0


def test_yaw_outside_dead_zone_scales_with_gain():
    controller = VisualServoController()
    # error_x = 740 - 640 = 100 px -> 100 * 0.035 = 3.5 deg/s
    yaw = controller.compute_yaw_rate(target_center_x=740)
    assert yaw == pytest.approx(3.5)


def test_yaw_rate_is_clamped_to_limit():
    controller = VisualServoController()
    yaw = controller.compute_yaw_rate(target_center_x=10_000)
    assert yaw == 30.0


def test_yaw_rate_negative_direction():
    controller = VisualServoController()
    yaw = controller.compute_yaw_rate(target_center_x=0)  # far left of center
    assert yaw < 0


def test_forward_speed_within_dead_zone_is_zero():
    controller = VisualServoController()
    # target_box_height_px = 300; height=290 -> error_distance=10 px, inside the 30 px dead zone
    assert controller.compute_forward_speed(target_box_height=290) == 0.0


def test_forward_speed_positive_when_target_too_small():
    controller = VisualServoController()
    # smaller box than target -> positive error -> move forward
    speed = controller.compute_forward_speed(target_box_height=100)
    assert speed > 0


def test_forward_speed_clamped_backward_limit():
    controller = VisualServoController()
    speed = controller.compute_forward_speed(target_box_height=10_000)
    assert speed == -1.0


def test_forward_speed_clamped_forward_limit():
    controller = VisualServoController()
    speed = controller.compute_forward_speed(target_box_height=-10_000)
    assert speed == 1.5


def test_down_speed_within_dead_zone_is_zero():
    controller = VisualServoController()
    # image_center_y = 360; target at 370 -> error_y=10, inside the 35 px dead zone
    assert controller.compute_down_speed(target_center_y=370) == 0.0


def test_down_speed_below_center_is_positive_descend():
    controller = VisualServoController()
    speed = controller.compute_down_speed(target_center_y=700)
    assert speed > 0


def test_down_speed_above_center_is_negative_climb():
    controller = VisualServoController()
    speed = controller.compute_down_speed(target_center_y=10)
    assert speed < 0


def test_altitude_protection_blocks_descent_at_floor():
    controller = VisualServoController()
    raw_down = controller.compute_down_speed(target_center_y=700)
    assert raw_down > 0
    protected = controller.apply_altitude_protection(raw_down, relative_altitude_m=2.5)
    assert protected == 0.0


def test_altitude_protection_allows_descent_above_floor():
    controller = VisualServoController()
    raw_down = controller.compute_down_speed(target_center_y=700)
    protected = controller.apply_altitude_protection(raw_down, relative_altitude_m=10.0)
    assert protected == raw_down


def test_altitude_protection_never_blocks_climb():
    controller = VisualServoController()
    raw_up = controller.compute_down_speed(target_center_y=10)
    protected = controller.apply_altitude_protection(raw_up, relative_altitude_m=2.5)
    assert protected == raw_up


def test_yaw_only_mode_forces_translation_to_zero():
    # Reproduces test_yaw.py: yaw is computed, forward/down are always zero.
    controller = VisualServoController(enable_translation=False)
    setpoint = controller.compute_setpoint(
        target_center_x=800,
        target_center_y=500,
        target_box_height=500,
        relative_altitude_m=10.0,
    )
    assert setpoint.forward == 0.0
    assert setpoint.down == 0.0
    assert setpoint.right == 0.0
    assert setpoint.yaw_rate != 0.0


def test_full_3d_mode_computes_all_axes():
    controller = VisualServoController(enable_translation=True)
    setpoint = controller.compute_setpoint(
        target_center_x=800,
        target_center_y=500,
        target_box_height=100,
        relative_altitude_m=10.0,
    )
    assert setpoint.yaw_rate > 0
    assert setpoint.forward > 0
    assert setpoint.down > 0


def test_zero_setpoint_is_all_zero():
    assert VisualServoController.zero_setpoint() == VelocitySetpoint()


def test_custom_config_overrides_defaults():
    # Reproduces the earlier Gazebo prototype's yaw gain (0.015) for comparison.
    gazebo_like = VisualServoConfig(yaw_gain=0.015, yaw_rate_limit_deg_s=20.0)
    controller = VisualServoController(config=gazebo_like)
    yaw = controller.compute_yaw_rate(target_center_x=740)  # error_x = 100
    assert yaw == pytest.approx(1.5)
