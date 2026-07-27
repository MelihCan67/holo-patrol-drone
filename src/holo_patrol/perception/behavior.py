"""
holo_patrol.perception.behavior
================================
Reference implementation of the Feature-Based Behavior Analysis state
machine described in ``docs/behavior_analysis.md``, Section 2.

The documented design classifies each tracked person into one of
three states based on face visibility and recognition outcome, rather
than raw movement speed (which is unreliable from a moving,
vibrating aerial platform):

- ``PERSON``            — face detected and matched against the authorized whitelist.
- ``FACE NOT VISIBLE``  — a human is detected but the face is currently obscured/turned away.
- ``MASK SUSPECT``      — the face stays unverifiable too long, escalating to a critical alarm.

This module contains no camera, DeepStream, or face-recognition
dependencies — it operates purely on the *outcome* of the face
verification pipeline (Dlib HOG + FaceNet, see ``docs/behavior_analysis.md``
Section 3), so it can be exercised in isolation and unit tested.
"""
from dataclasses import dataclass
from enum import Enum


class BehaviorState(str, Enum):
    PERSON = "PERSON"
    FACE_NOT_VISIBLE = "FACE NOT VISIBLE"
    MASK_SUSPECT = "MASK SUSPECT"


@dataclass(frozen=True)
class FaceVerificationResult:
    """Outcome of a single frame's face localization + verification step.

    ``obscured_duration_s`` is the length of time (in seconds) the
    target's face has been continuously undetected/unmatched, as
    tracked in temporal memory per ``docs/behavior_analysis.md``.
    """
    face_detected: bool
    face_recognized: bool
    obscured_duration_s: float = 0.0


def classify_behavior(
    result: FaceVerificationResult,
    obscured_threshold_s: float = 5.0,
) -> BehaviorState:
    """Classify a face-verification outcome into a ``BehaviorState``.

    - A detected AND recognized (whitelisted) face is always ``PERSON``.
    - An undetected/unrecognized face that has remained obscured for
      at least ``obscured_threshold_s`` seconds escalates to
      ``MASK_SUSPECT``.
    - Otherwise, the target is cached and flagged as ``FACE_NOT_VISIBLE``
      without triggering a critical alarm.
    """
    if result.face_detected and result.face_recognized:
        return BehaviorState.PERSON
    if result.obscured_duration_s >= obscured_threshold_s:
        return BehaviorState.MASK_SUSPECT
    return BehaviorState.FACE_NOT_VISIBLE


def requires_critical_alarm(state: BehaviorState) -> bool:
    """Whether a given behavior state should trigger a critical alarm
    (autonomous Visual Servoing tracking + Firebase alert), per the
    System Action column in ``docs/behavior_analysis.md``.
    """
    return state == BehaviorState.MASK_SUSPECT
