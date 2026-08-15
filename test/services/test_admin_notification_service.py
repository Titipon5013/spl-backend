"""Feature 4 admin notification pushes — mute, type filter, delivery dedupe."""

from datetime import datetime
from unittest.mock import MagicMock

from db.models import AdminAlertDelivery, AdminAlertSubscription, DeviceHealth, SystemAnomaly
from services.admin_notification_service import AdminNotificationService


def _sub(db, line_user_id="U1", muted=False, alert_types=None):
    sub = AdminAlertSubscription(
        line_user_id=line_user_id,
        muted=muted,
        alert_types=alert_types or "device_offline",
        linked_at=datetime.utcnow(),
    )
    db.add(sub)
    db.commit()
    return sub


def _anomaly(
    db,
    anomaly_type="device_offline",
    severity="warning",
    device_id="orange_pi_main_camera_1",
    lot_id=None,
    spot_id=None,
):
    row = SystemAnomaly(
        anomaly_type=anomaly_type,
        severity=severity,
        lot_id=lot_id,
        spot_id=spot_id,
        device_id=device_id,
        details="Device offline",
        detected_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_push_sent_to_unmuted_subscriber(db_session):
    _sub(db_session, "Uactive")
    db_session.add(
        DeviceHealth(
            device_id="orange_pi_main_camera_1",
            device_type="camera_1",
            status="offline",
            last_seen=datetime.utcnow(),
        )
    )
    db_session.commit()
    anomaly = _anomaly(db_session)
    pushes = []

    result = AdminNotificationService(
        db_session, push_fn=lambda uid, text: pushes.append((uid, text))
    ).dispatch_new_anomaly_alerts()

    assert result["pushed"] == 1
    assert pushes[0][0] == "Uactive"
    assert "อุปกรณ์หลุด" in pushes[0][1]
    assert "กล้อง 1" in pushes[0][1]
    assert "anomaly_id" not in pushes[0][1]
    assert anomaly.id is not None


def test_muted_subscriber_is_skipped(db_session):
    _sub(db_session, "Uquiet", muted=True)
    _anomaly(db_session)
    push = MagicMock()

    result = AdminNotificationService(db_session, push_fn=push).dispatch_new_anomaly_alerts()

    assert result["pushed"] == 0
    push.assert_not_called()


def test_stuck_slot_is_not_pushed_by_default(db_session, monkeypatch):
    monkeypatch.delenv("ADMIN_PUSH_ALERT_TYPES", raising=False)
    _sub(db_session, "U1", alert_types="stuck_slot,pipeline_inactive,device_offline")
    _anomaly(
        db_session,
        anomaly_type="stuck_slot",
        device_id=None,
        lot_id="CAMT_02",
        spot_id="C3",
    )
    push = MagicMock()

    result = AdminNotificationService(db_session, push_fn=push).dispatch_new_anomaly_alerts()

    assert result["pushed"] == 0
    assert result["skipped_type"] >= 1
    push.assert_not_called()


def test_alert_type_filter_skips_non_matching(db_session):
    _sub(db_session, "Udevice", alert_types="device_offline")
    _anomaly(
        db_session,
        anomaly_type="stuck_slot",
        device_id=None,
        lot_id="CAMT_01",
        spot_id="A1",
    )
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
