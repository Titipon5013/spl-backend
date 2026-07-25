from datetime import datetime, timedelta

import pytest

from db.models import DeviceHealth, ParkingEventLog, SystemAnomaly
from services.anomaly_service import (
    DEVICE_OFFLINE,
    PIPELINE_INACTIVE,
    STUCK_SLOT,
    AnomalyService,
)


def _event(db, spot_id, is_occupied, minutes_ago, lot_id="CAMT_01"):
    db.add(
        ParkingEventLog(
            lot_id=lot_id,
            spot_id=spot_id,
            is_occupied=is_occupied,
            timestamp=datetime.utcnow() - timedelta(minutes=minutes_ago),
        )
    )
    db.commit()


def _device(db, device_id, device_type, status, minutes_ago):
    db.add(
        DeviceHealth(
            device_id=device_id,
            device_type=device_type,
            status=status,
            last_seen=datetime.utcnow() - timedelta(minutes=minutes_ago),
        )
    )
    db.commit()


# ---------- URS-13 detection ----------

def test_detects_stuck_slot(db_session):
    # ช่องจอดที่รายงานว่ามีรถมา 20 ชั่วโมง เกินเกณฑ์ 12 ชั่วโมง
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    _event(db_session, "A2", False, minutes_ago=2)

    result = AnomalyService(db_session).detect_anomalies()

    stuck = (
        db_session.query(SystemAnomaly)
        .filter(SystemAnomaly.anomaly_type == STUCK_SLOT)
        .all()
    )
    assert result["new_anomalies"] >= 1
    assert [anomaly.spot_id for anomaly in stuck] == ["A1"]
    assert stuck[0].severity == "warning"


def test_does_not_flag_recently_occupied_slot(db_session):
    _event(db_session, "A1", True, minutes_ago=30)

    AnomalyService(db_session).detect_anomalies()

    assert (
        db_session.query(SystemAnomaly)
        .filter(SystemAnomaly.anomaly_type == STUCK_SLOT)
        .count()
        == 0
    )


def test_detects_pipeline_inactivity(db_session):
    _event(db_session, "A1", False, minutes_ago=45)

    AnomalyService(db_session).detect_anomalies()

    anomaly = (
        db_session.query(SystemAnomaly)
        .filter(SystemAnomaly.anomaly_type == PIPELINE_INACTIVE)
        .first()
    )
    assert anomaly is not None
    assert anomaly.lot_id == "CAMT_01"
    assert anomaly.severity == "critical"


def test_no_pipeline_anomaly_when_lot_never_reported(db_session):
    # ลานที่ยังไม่เคยส่งข้อมูลเลย ถือว่ายังไม่ได้ติดตั้ง ไม่ใช่ความผิดปกติ
    AnomalyService(db_session).detect_anomalies()

    assert (
        db_session.query(SystemAnomaly)
        .filter(SystemAnomaly.anomaly_type == PIPELINE_INACTIVE)
        .count()
        == 0
    )


def test_detects_offline_device(db_session):
    _device(db_session, "orange_pi_main", "board", "online", minutes_ago=30)
    _device(db_session, "orange_pi_main_cam1", "camera_1", "online", minutes_ago=0)

    AnomalyService(db_session).detect_anomalies()

    anomalies = (
        db_session.query(SystemAnomaly)
        .filter(SystemAnomaly.anomaly_type == DEVICE_OFFLINE)
        .all()
    )
    assert [anomaly.device_id for anomaly in anomalies] == ["orange_pi_main"]
    # บอร์ดดับถือว่าร้ายแรงกว่ากล้องดับ
    assert anomalies[0].severity == "critical"


# ---------- dedupe and auto-resolve ----------

def test_repeated_scan_does_not_duplicate_open_anomaly(db_session):
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    service = AnomalyService(db_session)

    service.detect_anomalies()
    second = service.detect_anomalies()

    assert second["new_anomalies"] == 0
    assert (
        db_session.query(SystemAnomaly)
        .filter(SystemAnomaly.anomaly_type == STUCK_SLOT)
        .count()
        == 1
    )


def test_anomaly_auto_resolves_when_condition_clears(db_session):
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    service = AnomalyService(db_session)
    service.detect_anomalies()

    # รถออกจากช่องจอดแล้ว ความผิดปกติควรถูกปิดอัตโนมัติ
    _event(db_session, "A1", False, minutes_ago=0)
    result = service.detect_anomalies()

    stuck = (
        db_session.query(SystemAnomaly)
        .filter(SystemAnomaly.anomaly_type == STUCK_SLOT)
        .first()
    )
    assert result["resolved_anomalies"] >= 1
    assert stuck.resolved_at is not None


# ---------- URS-13 retrieval / URS-14 review ----------

def test_get_anomalies_hides_reviewed_by_default(db_session):
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    service = AnomalyService(db_session)
    service.detect_anomalies()

    anomaly_id = service.get_anomalies(anomaly_type=STUCK_SLOT)[0]["anomaly_id"]
    service.mark_anomaly_reviewed(anomaly_id, "admin@camt.cmu.ac.th")

    assert service.get_anomalies(anomaly_type=STUCK_SLOT) == []
    assert len(service.get_anomalies(anomaly_type=STUCK_SLOT, include_reviewed=True)) == 1


def test_mark_anomaly_reviewed_records_reviewer(db_session):
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    service = AnomalyService(db_session)
    service.detect_anomalies()
    anomaly_id = service.get_anomalies(anomaly_type=STUCK_SLOT)[0]["anomaly_id"]

    reviewed = service.mark_anomaly_reviewed(anomaly_id, "admin@camt.cmu.ac.th")

    assert reviewed["reviewed_by"] == "admin@camt.cmu.ac.th"
    assert reviewed["reviewed_at"] is not None


def test_mark_anomaly_reviewed_returns_none_for_unknown_id(db_session):
    assert AnomalyService(db_session).mark_anomaly_reviewed(9999, "admin@camt.cmu.ac.th") is None


def test_get_anomalies_filters_by_type(db_session):
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    _device(db_session, "orange_pi_main", "board", "offline", minutes_ago=30)
    service = AnomalyService(db_session)
    service.detect_anomalies()

    device_only = service.get_anomalies(anomaly_type=DEVICE_OFFLINE)

    assert len(device_only) == 1
    assert device_only[0]["anomaly_type"] == DEVICE_OFFLINE
