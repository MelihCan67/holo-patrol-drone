from holo_patrol.cloud.alerts import AlertPayload, AlertThrottle


def test_first_alert_always_sends():
    throttle = AlertThrottle(cooldown_s=15.0)
    assert throttle.should_send(now=0.0)


def test_alert_blocked_within_cooldown_window():
    throttle = AlertThrottle(cooldown_s=15.0)
    throttle.mark_sent(now=100.0)
    assert not throttle.should_send(now=105.0)


def test_alert_allowed_immediately_after_cooldown_expires():
    throttle = AlertThrottle(cooldown_s=15.0)
    throttle.mark_sent(now=100.0)
    assert throttle.should_send(now=116.0)


def test_alert_payload_builds_expected_firestore_fields():
    payload = AlertPayload(
        title="🚨 Target Tracking Started",
        message="Drone locked onto track ID 7.",
        track_id=7,
        confidence=0.95,
    )
    doc = payload.to_firestore_dict(image_url="https://example.com/img.jpg")

    assert doc["title"] == "🚨 Target Tracking Started"
    assert doc["message"] == "Drone locked onto track ID 7."
    assert doc["imageURL"] == "https://example.com/img.jpg"
    assert doc["id"] == 7
    assert isinstance(doc["id"], int)
    assert doc["locationName"] == "Drone Ana Kamera"
    assert doc["severity"] == "critical"
    assert doc["isActive"] is True
    assert doc["confidence"] == 0.95


def test_alert_payload_custom_fields():
    payload = AlertPayload(
        title="t",
        message="m",
        track_id=3,
        confidence=0.5,
        location_name="North Perimeter",
        severity="warning",
        is_active=False,
    )
    doc = payload.to_firestore_dict(image_url="https://example.com/a.jpg")
    assert doc["locationName"] == "North Perimeter"
    assert doc["severity"] == "warning"
    assert doc["isActive"] is False
