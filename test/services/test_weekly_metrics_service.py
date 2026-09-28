"""Unit tests for the Feature 5 weekly summary service."""

from datetime import datetime, timedelta

from db.models import WeeklyLotMetric
from services.weekly_metrics_service import last_completed_utc_week, record_weekly_metrics


def test_last_completed_utc_week_from_monday_morning():
    now = datetime(2026, 9, 28, 8, 0)  # Monday 08:00

    start, end = last_completed_utc_week(now)

    assert (start, end) == (datetime(2026, 9, 21), datetime(2026, 9, 28))
    assert end - start == timedelta(days=7)


def test_last_completed_utc_week_midweek_and_sunday():
    midweek = datetime(2026, 9, 30, 12, 0)  # Wednesday
    sunday = datetime(2026, 9, 27, 23, 0)  # week Sep21-28 still in progress

    assert last_completed_utc_week(midweek) == (
        datetime(2026, 9, 21),
        datetime(2026, 9, 28),
    )
    assert last_completed_utc_week(sunday) == (
        datetime(2026, 9, 14),
        datetime(2026, 9, 21),
    )


def test_record_weekly_metrics_upserts_same_row(db_session):
    start = datetime(2026, 9, 21)
    end = datetime(2026, 9, 28)
    metrics = {
        "utilization_percentage": 50.0,
        "peak_occupancy": 15,
        "vehicle_count": 4,
        "avg_dwell_time_minutes": 30.0,
    }

    row = record_weekly_metrics(db_session, "CAMT_01", start, end, metrics)
    row_id = row.id
    assert db_session.query(WeeklyLotMetric).count() == 1

    updated_metrics = dict(metrics, vehicle_count=9, utilization_percentage=55.5)
    row2 = record_weekly_metrics(db_session, "CAMT_01", start, end, updated_metrics)

    assert row2.id == row_id
    assert db_session.query(WeeklyLotMetric).count() == 1
    assert row2.vehicle_count == 9
    assert row2.utilization_percentage == 55.5
