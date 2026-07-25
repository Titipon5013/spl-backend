"""Tests for the AnalyticsService methods added for Feature 2 (URS-08, URS-09, URS-12)."""

from datetime import datetime, timedelta

from db.models import ParkingEventLog, ParkingSnapshot
from services.analytics_service import AnalyticsService


def _snapshot(db, occupied=23, available=7, minutes_ago=0):
    db.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=datetime.utcnow() - timedelta(minutes=minutes_ago),
            available_spaces=available,
            total_spaces=30,
            occupied_spaces=occupied,
            occupacy_rate=round(occupied / 30 * 100, 2),
            confidence=0.95,
            processing_time_seconds=0.4,
        )
    )
    db.commit()


def _event(db, spot_id, is_occupied, minutes_ago=0, lot_id="CAMT_01"):
    db.add(
        ParkingEventLog(
            lot_id=lot_id,
            spot_id=spot_id,
            is_occupied=is_occupied,
            timestamp=datetime.utcnow() - timedelta(minutes=minutes_ago),
        )
    )
    db.commit()


# ---------- URS-08 ----------

def test_get_live_occupancy_returns_latest_snapshot(db_session):
    _snapshot(db_session, occupied=10, available=20, minutes_ago=60)
    _snapshot(db_session, occupied=23, available=7, minutes_ago=1)

    result = AnalyticsService(db_session).get_live_occupancy("CAMT_01")

    assert result["occupied_spaces"] == 23
    assert result["available_spaces"] == 7
    assert result["occupancy_rate"] == 76.67
    assert result["data_age_seconds"] >= 0


def test_get_live_occupancy_returns_none_when_no_data(db_session):
    assert AnalyticsService(db_session).get_live_occupancy("CAMT_01") is None


# ---------- URS-09 ----------

def test_check_slot_status_uses_most_recent_event(db_session):
    _event(db_session, "A1", True, minutes_ago=90)
    _event(db_session, "A1", False, minutes_ago=5)

    result = AnalyticsService(db_session).check_slot_status("CAMT_01", "A1")

    assert result["state"] == "free"
    assert result["duration_minutes"] >= 4


def test_check_slot_status_returns_none_for_unknown_slot(db_session):
    _event(db_session, "A1", True)

    assert AnalyticsService(db_session).check_slot_status("CAMT_01", "ZZ9") is None


# ---------- URS-12 ----------

def test_find_available_slots_reflects_latest_state_per_spot(db_session):
    _event(db_session, "A1", True, minutes_ago=30)
    _event(db_session, "A2", True, minutes_ago=30)
    _event(db_session, "A3", False, minutes_ago=30)
    # A2 ว่างแล้ว ต้องนับจากเหตุการณ์ล่าสุดเท่านั้น
    _event(db_session, "A2", False, minutes_ago=1)

    result = AnalyticsService(db_session).find_available_slots("CAMT_01")

    assert result["available_spots"] == ["A2", "A3"]
    assert result["available_count"] == 2
    assert result["occupied_count"] == 1
    assert result["known_spots"] == 3


def test_find_available_slots_ignores_other_lots(db_session):
    _event(db_session, "A1", False, lot_id="CAMT_01")
    _event(db_session, "B1", False, lot_id="CAMT_02")

    result = AnalyticsService(db_session).find_available_slots("CAMT_01")

    assert result["available_spots"] == ["A1"]


def test_find_available_slots_empty_when_no_events(db_session):
    result = AnalyticsService(db_session).find_available_slots("CAMT_01")

    assert result["known_spots"] == 0
    assert result["available_spots"] == []
