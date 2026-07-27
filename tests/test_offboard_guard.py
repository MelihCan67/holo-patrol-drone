from holo_patrol.flight_control.offboard_guard import OffboardGuard, build_zero_setpoint_stream
from holo_patrol.flight_control.visual_servo import VelocitySetpoint


def test_starts_unauthorized():
    guard = OffboardGuard()
    assert not guard.is_authorized()


def test_offboard_mode_grants_authorization():
    guard = OffboardGuard()
    changed = guard.update_flight_mode("FlightMode.OFFBOARD")
    assert changed
    assert guard.is_authorized()


def test_guided_mode_also_grants_authorization():
    guard = OffboardGuard()
    guard.update_flight_mode("GUIDED")
    assert guard.is_authorized()


def test_unrelated_mode_does_not_grant_authorization():
    guard = OffboardGuard()
    changed = guard.update_flight_mode("POSITION")
    assert not changed
    assert not guard.is_authorized()


def test_leaving_offboard_revokes_authorization():
    guard = OffboardGuard()
    guard.update_flight_mode("OFFBOARD")
    assert guard.is_authorized()
    changed = guard.update_flight_mode("HOLD")
    assert changed
    assert not guard.is_authorized()


def test_repeated_same_mode_reports_no_change():
    guard = OffboardGuard()
    guard.update_flight_mode("OFFBOARD")
    changed_again = guard.update_flight_mode("OFFBOARD")
    assert not changed_again
    assert guard.is_authorized()


def test_zero_setpoint_stream_default_length_matches_onboard_scripts():
    stream = build_zero_setpoint_stream()
    assert len(stream) == 10
    assert all(sp == VelocitySetpoint() for sp in stream)


def test_zero_setpoint_stream_custom_length_matches_gazebo_prototype():
    stream = build_zero_setpoint_stream(count=15)
    assert len(stream) == 15
