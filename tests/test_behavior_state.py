from holo_patrol.perception.behavior import (
    BehaviorState,
    FaceVerificationResult,
    classify_behavior,
    requires_critical_alarm,
)


def test_recognized_face_is_classified_as_person():
    result = FaceVerificationResult(face_detected=True, face_recognized=True)
    assert classify_behavior(result) == BehaviorState.PERSON


def test_detected_but_unrecognized_face_briefly_is_not_critical():
    result = FaceVerificationResult(
        face_detected=True, face_recognized=False, obscured_duration_s=1.0
    )
    state = classify_behavior(result)
    assert state == BehaviorState.FACE_NOT_VISIBLE
    assert not requires_critical_alarm(state)


def test_briefly_obscured_face_is_face_not_visible():
    result = FaceVerificationResult(
        face_detected=False, face_recognized=False, obscured_duration_s=1.0
    )
    state = classify_behavior(result)
    assert state == BehaviorState.FACE_NOT_VISIBLE
    assert not requires_critical_alarm(state)


def test_prolonged_obscured_face_escalates_to_mask_suspect():
    result = FaceVerificationResult(
        face_detected=False, face_recognized=False, obscured_duration_s=6.0
    )
    state = classify_behavior(result)
    assert state == BehaviorState.MASK_SUSPECT
    assert requires_critical_alarm(state)


def test_custom_threshold_is_respected():
    result = FaceVerificationResult(
        face_detected=False, face_recognized=False, obscured_duration_s=2.5
    )
    assert classify_behavior(result, obscured_threshold_s=2.0) == BehaviorState.MASK_SUSPECT
    assert classify_behavior(result, obscured_threshold_s=3.0) == BehaviorState.FACE_NOT_VISIBLE


def test_only_person_state_requires_no_alarm():
    for state in BehaviorState:
        expected = state == BehaviorState.MASK_SUSPECT
        assert requires_critical_alarm(state) == expected
