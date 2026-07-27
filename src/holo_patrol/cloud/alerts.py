"""
holo_patrol.cloud.alerts
=========================
Cooldown and payload-shaping logic for Firebase alert uploads,
decoupled from the Firebase Admin SDK itself so it can be unit-tested
without cloud credentials or network access.

Mirrors ``ALERT_SAVE_COOLDOWN`` and the Firestore document fields
written by ``send_alert_to_firebase`` in ``test_yaw.py`` /
``test_3d_tracker.py`` (see docs/software_setup.md, Section 6).
"""
from dataclasses import dataclass, field


@dataclass
class AlertThrottle:
    """Prevents uploading a new alert image on every processed frame.

    Matches the 15-second cooldown (``ALERT_SAVE_COOLDOWN``) used
    onboard. Call ``should_send(now)`` before triggering an upload,
    and ``mark_sent(now)`` immediately after a successful upload is
    kicked off.
    """
    cooldown_s: float = 15.0
    _last_sent: float = field(default=float("-inf"), repr=False)

    def should_send(self, now: float) -> bool:
        return (now - self._last_sent) > self.cooldown_s

    def mark_sent(self, now: float) -> None:
        self._last_sent = now


@dataclass(frozen=True)
class AlertPayload:
    """Shapes a Firestore alert document.

    Field names match ``send_alert_to_firebase`` in the onboard
    scripts exactly: ``title``, ``message``, ``timestamp`` (added by
    the caller as ``firestore.SERVER_TIMESTAMP``), ``imageURL``,
    ``id``, ``locationName``, ``severity``, ``isActive``, ``confidence``.
    """
    title: str
    message: str
    track_id: int
    confidence: float
    location_name: str = "Drone Ana Kamera"
    severity: str = "critical"
    is_active: bool = True

    def to_firestore_dict(self, image_url: str) -> dict:
        """Build the Firestore document fields for this alert.

        The caller is responsible for adding ``timestamp`` (typically
        ``firestore.SERVER_TIMESTAMP``) before writing the document,
        since that value is only meaningful in a live Firestore
        client and is intentionally kept out of this pure-Python
        payload builder.
        """
        return {
            "title": self.title,
            "message": self.message,
            "imageURL": image_url,
            "id": int(self.track_id),
            "locationName": self.location_name,
            "severity": self.severity,
            "isActive": self.is_active,
            "confidence": float(self.confidence),
        }
