"""Boundary-condition tests.

Covers the exact edges of the dead zones, the altitude floor, and the
alert cooldown, plus degenerate/corrupted inputs (zero/negative bounding
boxes, NaN and infinite telemetry) that the "happy path" tests in
test_visual_servo.py, test_perception.py, and test_alerts.py don't
exercise.
"""
import math

from holo_patrol.cloud.alerts import AlertThrottle
from holo_patrol.flight_control.visual_servo import VisualServoController
from holo_patrol.perception.detection import Detection, TargetSelector

# --- Exact dead-zone boundaries ---
# The dead-zone checks use strict "<" (abs(error) < dead_zone), so a value
# exactly equal to the dead zone is OUTSIDE it and should produce a nonzero
# command, not a zero one.

def test_yaw_exactly_at_dead_zone_boundary_is_not_zero():
    controller = VisualServoController()
    # image_center_x = 640; target at 680 -> error_x = 40 px, exactly the dead zone
    yaw = controller.compute_yaw_rate(target_center_x=680)
    assert yaw != 0.0


def test_yaw_just_inside_dead_zone_boundary_is_zero():
    controller = VisualServoController()
    yaw = controller.compute_yaw_rate(target_center_x=679.999)
    assert yaw == 0.0


def test_forward_exactly_at_distance_dead_zone_boundary_is_not_zero():
    controller = VisualServoController()
    # target_box_height_px = 300; height=270 -> error_distance=30 px, exactly the dead zone
    speed = controller.compute_forward_speed(target_box_height=270)
    assert speed != 0.0


def test_down_exactly_at_vertical_dead_zone_boundary_is_not_zero():
    controller = VisualServoController()
    # image_center_y = 360; target at 395 -> error_y = 35 px, exactly the dead zone
    speed = controller.compute_down_speed(target_center_y=395)
    assert speed != 0.0


# --- Exact altitude floor ---

def test_altitude_exactly_at_floor_blocks_descent():
    controller = VisualServoController()
    result = controller.apply_altitude_protection(down_speed=0.4, relative_altitude_m=3.0)
    assert result == 0.0


def test_altitude_just_above_floor_allows_descent():
    controller = VisualServoController()
    result = controller.apply_altitude_protection(down_speed=0.4, relative_altitude_m=3.01)
    assert result == 0.4


# --- NaN / infinite telemetry ---

def test_nan_altitude_blocks_descent():
    controller = VisualServoController()
    result = controller.apply_altitude_protection(down_speed=0.4, relative_altitude_m=float("nan"))
    assert result == 0.0


def test_nan_altitude_never_blocks_climb():
    controller = VisualServoController()
    result = controller.apply_altitude_protection(down_speed=-0.4, relative_altitude_m=float("nan"))
    assert result == -0.4


def test_positive_infinite_altitude_allows_descent():
    controller = VisualServoController()
    result = controller.apply_altitude_protection(down_speed=0.4, relative_altitude_m=float("inf"))
    assert result == 0.4


def test_negative_infinite_altitude_blocks_descent():
    controller = VisualServoController()
    result = controller.apply_altitude_protection(down_speed=0.4, relative_altitude_m=float("-inf"))
    assert result == 0.0


# --- Exact alert cooldown boundary ---

def test_alert_exactly_at_cooldown_boundary_is_still_blocked():
    # should_send uses strict ">", so exactly `cooldown_s` elapsed is NOT yet allowed.
    throttle = AlertThrottle(cooldown_s=15.0)
    throttle.mark_sent(now=100.0)
    assert not throttle.should_send(now=115.0)


def test_alert_just_past_cooldown_boundary_is_allowed():
    throttle = AlertThrottle(cooldown_s=15.0)
    throttle.mark_sent(now=100.0)
    assert throttle.should_send(now=115.001)


# --- Degenerate bounding boxes ---

def test_zero_size_bounding_box_is_still_selectable():
    selector = TargetSelector()
    det = Detection(class_id=0, confidence=0.9, x1=100, y1=100, x2=100, y2=100, track_id=1)
    best = selector.select([det])
    assert best is not None
    assert best.width == 0
    assert best.height == 0


def test_negative_size_bounding_box_does_not_crash_selection_or_servo():
    # x2 < x1 / y2 < y1 can happen if upstream coordinates are corrupted.
    # The selector and controller must not raise; they should just produce
    # a (harmless) negative width/height and a correspondingly-signed error.
    selector = TargetSelector()
    det = Detection(class_id=0, confidence=0.9, x1=200, y1=200, x2=100, y2=100, track_id=2)
    best = selector.select([det])
    assert best.width == -100
    assert best.height == -100

    controller = VisualServoController()
    setpoint = controller.compute_setpoint(
        target_center_x=best.center_x,
        target_center_y=best.center_y,
        target_box_height=best.height,
        relative_altitude_m=10.0,
    )
    assert math.isfinite(setpoint.forward)
    assert math.isfinite(setpoint.down)
    assert math.isfinite(setpoint.yaw_rate)
