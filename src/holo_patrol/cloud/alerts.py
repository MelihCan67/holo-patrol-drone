"""
holo_patrol.cloud.alerts
=========================
Cooldown and payload-shaping logic for Firebase alert uploads,
decoupled from the Firebase Admin SDK itself so it can be unit-tested
without cloud credentials or network access.

Mirrors ``ALERT_SAVE_COOLDOWN`` and the Firestore document fields
written by ``send_alert_to_firebase`` in ``yaw_tracker.py`` /
``visual_tracker_3d.py`` (see docs/software_setup.md, Section 6).
"""
from dataclasses import dataclass, field
from typing import Optional

# Single source of truth for how long an evidence-image signed URL stays valid.
# Keep this short and pair it with an explicit Cloud Storage lifecycle/retention
# policy on the bucket itself -- a multi-year signed URL outlives any reasonable
# evidence-retention window and, if leaked, grants long-lived access to the image.
# Both onboard scripts (yaw_tracker.py, visual_tracker_3d.py) import this constant
# instead of hardcoding their own expiration window.
EVIDENCE_URL_TTL_DAYS = 7


@dataclass
class AlertThrottle:
    """Prevents uploading a new alert image on every processed frame.

    Matches the 15-second cooldown (``ALERT_SAVE_COOLDOWN``) used
    onboard. Call ``should_send(now)`` before triggering an upload,
    and ``mark_sent(now)`` immediately after a successful upload is
    kicked off.

    Optionally pass a ``track_id`` to both calls to additionally apply
    a longer, per-track cooldown (``same_track_cooldown_s``, default
    4x ``cooldown_s``) on top of the global one. `track_id` continuity
    isn't guaranteed by the onboard IOU tracker (see
    docs/visual_servoing.md, Section 6) -- if the same physical target
    keeps re-appearing under a new ID, the global cooldown alone would
    still fire a fresh "critical" alert on every re-identification.
    Passing `track_id` catches the common case where the *same* ID
    reappears quickly, without changing behavior for callers that
    don't pass it.
    """
    cooldown_s: float = 15.0
    same_track_cooldown_s: Optional[float] = None
    _last_sent: float = field(default=float("-inf"), repr=False)
    _last_sent_by_track: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.same_track_cooldown_s is None:
            self.same_track_cooldown_s = self.cooldown_s * 4

    def should_send(self, now: float, track_id: Optional[int] = None) -> bool:
        if track_id is not None:
            last_for_track = self._last_sent_by_track.get(track_id, float("-inf"))
            if (now - last_for_track) <= self.same_track_cooldown_s:
                return False
        return (now - self._last_sent) > self.cooldown_s

    def mark_sent(self, now: float, track_id: Optional[int] = None) -> None:
        self._last_sent = now
        if track_id is not None:
            self._last_sent_by_track[track_id] = now


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
