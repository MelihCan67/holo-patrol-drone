from holo_patrol.perception.target_state import TargetState


def test_default_state_is_not_detected():
    state = TargetState()
    assert state.detected is False
    assert state.is_fresh(now=0.0, timeout_s=0.4) is False


def test_none_helper_matches_default_state():
    assert TargetState.none() == TargetState()


def test_fresh_detection_within_timeout_window():
    state = TargetState(
        detected=True, center_x=640, center_y=360, height=300, track_id=7, detected_at=100.0
    )
    assert state.is_fresh(now=100.2, timeout_s=0.4) is True


def test_stale_detection_outside_timeout_window():
    state = TargetState(
        detected=True, center_x=640, center_y=360, height=300, track_id=7, detected_at=100.0
    )
    assert state.is_fresh(now=100.5, timeout_s=0.4) is False


def test_undetected_state_is_never_fresh_even_within_window():
    state = TargetState(detected=False, detected_at=100.0)
    assert state.is_fresh(now=100.1, timeout_s=0.4) is False
