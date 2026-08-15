"""Feature 4 admin notification pushes — mute, type filter, delivery dedupe."""

from datetime import datetime
from unittest.mock import MagicMock

from db.models import AdminAlertDelivery, AdminAlertSubscription, SystemAnomaly
from services.admin_notification_service import AdminNotificationService


def _sub(db, line_user_id="U1", muted=False, alert_types=None):
    sub = AdminAlertSubscription(
        line_user_id=line_user_id,
        muted=muted,
        alert_types=alert_types or "stuck_slot,pipeline_inactive,device_offline",
        linked_at=datetime.utcnow(),
    )
    db.add(sub)
    db.commit()
    return sub


def _anomaly(db, anomaly_type="stuck_slot", severity="warning"):
    row = SystemAnomaly(
        anomaly_type=anomaly_type,
        severity=severity,
        lot_id="CAMT_01",
        spot_id="A1",
        device_id=None,
        details="Slot A1 stuck",
        detected_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_push_sent_to_unmuted_subscriber(db_session):
    _sub(db_session, "Uactive")
    anomaly = _anomaly(db_session)
    pushes = []

    result = AdminNotificationService(
        db_session, push_fn=lambda uid, text: pushes.append((uid, text))
    ).dispatch_new_anomaly_alerts()

    assert result["pushed"] == 1
    assert pushes[0][0] == "Uactive"
    assert "stuck_slot" in pushes[0][1]
    assert f"anomaly_id={anomaly.id}" in pushes[0][1]


def test_muted_subscriber_is_skipped(db_session):
    _sub(db_session, "Uquiet", muted=True)
    _anomaly(db_session)
    push = MagicMock()

    result = AdminNotificationService(db_session, push_fn=push).dispatch_new_anomaly_alerts()

    assert result["pushed"] == 0
    push.assert_not_called()


def test_alert_type_filter_skips_non_matching(db_session):
    _sub(db_session, "Udevice", alert_types="device_offline")
    _anomaly(db_session, anomaly_type="stuck_slot")
    push = MagicMock()

    result = AdminNotificationService(db_session, push_fn=push).dispatch_new_anomaly_alerts()

    assert result["pushed"] == 0
    assert result["skipped_type"] >= 1
    push.assert_not_called()


def test_delivery_dedupe_prevents_second_push(db_session):
    _sub(db_session, "U1")
    anomaly = _anomaly(db_session)
    pushes = []

    service = AdminNotificationService(
        db_session, push_fn=lambda uid, text: pushes.append(uid)
    )
    first = service.dispatch_new_anomaly_alerts()
    second = service.dispatch_new_anomaly_alerts()

    assert first["pushed"] == 1
    assert second["pushed"] == 0
    assert second["skipped_dup"] >= 1
    assert len(pushes) == 1
    assert (
        db_session.query(AdminAlertDelivery)
        .filter(
            AdminAlertDelivery.anomaly_id == anomaly.id,
            AdminAlertDelivery.line_user_id == "U1",
        )
        .count()
        == 1
    )
