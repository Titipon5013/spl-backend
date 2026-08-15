"""Feature 4 admin webhook commands — /link /mute /unmute /settings."""

from datetime import datetime

import pytest

from db.models import AdminAlertSubscription
from routes.admin_webhook_controller import handle_admin_command


@pytest.fixture
def link_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_LINE_LINK_SECRET", "parkpilot-link")
    return "parkpilot-link"


def test_link_creates_subscription(db_session, link_secret):
    reply = handle_admin_command(db_session, "Unew", f"/link {link_secret}")

    assert "Linked" in reply
    sub = (
        db_session.query(AdminAlertSubscription)
        .filter(AdminAlertSubscription.line_user_id == "Unew")
        .one()
    )
    assert sub.muted is False


def test_link_rejects_bad_secret(db_session, link_secret):
    reply = handle_admin_command(db_session, "Unew", "/link wrong")

    assert "Invalid" in reply
    assert db_session.query(AdminAlertSubscription).count() == 0


def test_mute_unmute_and_settings(db_session, link_secret):
    handle_admin_command(db_session, "U1", f"/link {link_secret}")

    mute_reply = handle_admin_command(db_session, "U1", "/mute")
    assert "muted" in mute_reply.lower()
    assert (
        db_session.query(AdminAlertSubscription)
        .filter(AdminAlertSubscription.line_user_id == "U1")
        .one()
        .muted
        is True
    )

    unmute_reply = handle_admin_command(db_session, "U1", "/unmute")
    assert "unmuted" in unmute_reply.lower()

    settings = handle_admin_command(db_session, "U1", "/settings")
    assert "active" in settings
    assert "U1" in settings


def test_commands_require_link_first(db_session, link_secret):
    reply = handle_admin_command(db_session, "Ustranger", "/mute")
    assert "/link" in reply


def test_non_command_returns_none(db_session, link_secret):
    assert handle_admin_command(db_session, "U1", "how full is CAMT_01?") is None


def test_anomaly_job_invokes_notification_dispatch(monkeypatch, db_session):
    from services import report_scheduler

    class FakeAnomalyService:
        def __init__(self, db):
            self.db = db

        def detect_anomalies(self):
            return {
                "detected_at": datetime.utcnow().isoformat(),
                "new_anomalies": 1,
                "resolved_anomalies": 0,
                "open_anomalies": 1,
            }

    called = {}

    class FakeNotify:
        def __init__(self, db):
            called["db"] = db

        def dispatch_new_anomaly_alerts(self):
            called["dispatched"] = True
            return {
                "pushed": 1,
                "failures": 0,
                "skipped_dup": 0,
                "skipped_muted": 0,
                "skipped_type": 0,
                "open_anomalies": 1,
                "subscriptions": 1,
            }

    monkeypatch.setattr(report_scheduler, "AnomalyService", FakeAnomalyService)
    monkeypatch.setattr(report_scheduler, "Session", lambda: db_session)
    monkeypatch.setattr(
        "services.admin_notification_service.AdminNotificationService",
        FakeNotify,
    )

    report_scheduler.trigger_anomaly_detection_now()

    assert called.get("dispatched") is True
