from holo_patrol.cloud.alerts import EVIDENCE_URL_TTL_DAYS, AlertPayload, AlertThrottle


def test_evidence_url_ttl_is_short_lived():
    # Guards against a regression back to a multi-year signed URL: the
    # onboard scripts should both import this single constant rather than
    # hardcoding their own (and possibly inconsistent) expiration window.
    assert 0 < EVIDENCE_URL_TTL_DAYS <= 30


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


def test_track_id_is_optional_and_does_not_change_default_behavior():
    throttle = AlertThrottle(cooldown_s=15.0)
    throttle.mark_sent(now=100.0)
    assert not throttle.should_send(now=105.0)
    assert throttle.should_send(now=116.0)


def test_same_track_id_blocked_longer_than_global_cooldown():
    # Default same_track_cooldown_s is 4x cooldown_s, so a re-appearance of the
    # *same* track_id well past the global 15s cooldown is still suppressed.
    throttle = AlertThrottle(cooldown_s=15.0)
    throttle.mark_sent(now=100.0, track_id=7)
    assert not throttle.should_send(now=120.0, track_id=7)  # past global, not per-track
    assert throttle.should_send(now=161.0, track_id=7)  # past 4x cooldown


def test_different_track_id_only_bound_by_global_cooldown():
    throttle = AlertThrottle(cooldown_s=15.0)
    throttle.mark_sent(now=100.0, track_id=7)
    assert not throttle.should_send(now=110.0, track_id=8)  # global cooldown still active
    assert throttle.should_send(now=116.0, track_id=8)  # global cooldown expired


def test_custom_same_track_cooldown():
    throttle = AlertThrottle(cooldown_s=15.0, same_track_cooldown_s=30.0)
    throttle.mark_sent(now=100.0, track_id=1)
    assert not throttle.should_send(now=125.0, track_id=1)
    assert throttle.should_send(now=131.0, track_id=1)


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
