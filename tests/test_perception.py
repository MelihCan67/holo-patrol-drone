from holo_patrol.perception.detection import PERSON_CLASS_ID, Detection, TargetSelector


def test_selects_highest_confidence_person():
    detections = [
        Detection(class_id=PERSON_CLASS_ID, confidence=0.40, x1=0, y1=0, x2=10, y2=10, track_id=1),
        Detection(class_id=PERSON_CLASS_ID, confidence=0.90, x1=5, y1=5, x2=25, y2=45, track_id=2),
        Detection(class_id=2, confidence=0.99, x1=0, y1=0, x2=100, y2=100, track_id=3),  # e.g. car
    ]
    best = TargetSelector().select(detections)
    assert best is not None
    assert best.track_id == 2


def test_returns_none_when_no_person_present():
    detections = [Detection(class_id=2, confidence=0.99, x1=0, y1=0, x2=100, y2=100)]
    assert TargetSelector().select(detections) is None


def test_returns_none_for_empty_frame():
    assert TargetSelector().select([]) is None


def test_custom_target_class_id():
    detections = [
        Detection(class_id=0, confidence=0.95, x1=0, y1=0, x2=10, y2=10),
        Detection(class_id=7, confidence=0.50, x1=0, y1=0, x2=10, y2=10),
    ]
    selector = TargetSelector(target_class_id=7)
    best = selector.select(detections)
    assert best is not None
    assert best.class_id == 7


def test_detection_geometry_helpers():
    d = Detection(class_id=0, confidence=0.8, x1=100, y1=200, x2=300, y2=500)
    assert d.center_x == 200
    assert d.center_y == 350
    assert d.height == 300
    assert d.width == 200
