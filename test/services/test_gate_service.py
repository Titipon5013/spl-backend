from datetime import datetime, timezone

from db.models import GateEvent
from schemas.gate import GateEventPayload
from services.gate_service import GateService


def test_gate_event_is_deduplicated_and_counted(db_session):
    timestamp = datetime(2026, 10, 7, 12, 0)
    service = GateService(db_session)
    payload = GateEventPayload(
        event="open",
        event_id="evt-1",
        gate_id="CAMT_EXIT_01",
        vehicle_class="car",
        confidence=0.88,
        timestamp=timestamp,
    )

    assert service.record_event(payload) == "saved"
    assert service.record_event(payload) == "duplicate_ignored"
    service.record_event(
        GateEventPayload(
            event="close",
            event_id="evt-2",
            gate_id="CAMT_EXIT_01",
            vehicle_class="car",
            confidence=0.88,
            timestamp=timestamp,
        )
    )

    assert db_session.query(GateEvent).count() == 2
    assert service.get_daily_count(timestamp) == {
        "open_count": 1,
        "close_count": 1,
        "count_gap": 0,
        "has_missing_message": False,
    }


def test_gate_count_flags_missing_message(db_session):
    timestamp = datetime(2026, 10, 7, 12, 0)
    service = GateService(db_session)
    service.record_event(
        GateEventPayload(event="open", event_id="evt-1", gate_id="CAMT_EXIT_01", timestamp=timestamp)
    )
    service.record_event(
        GateEventPayload(event="open", event_id="evt-2", gate_id="CAMT_EXIT_01", timestamp=timestamp)
    )
    service.record_event(
        GateEventPayload(event="open", event_id="evt-3", gate_id="CAMT_EXIT_01", timestamp=timestamp)
    )

    result = service.get_daily_count(timestamp)
    assert result["count_gap"] == 3
    assert result["has_missing_message"] is True


def test_gate_count_endpoint_reads_events_from_database(client, db_session):
    timestamp = datetime(2026, 10, 7, 12, 0)
    db_session.add_all(
        [
            GateEvent(event="open", event_id="evt-api-1", gate_id="CAMT_EXIT_01", timestamp=timestamp),
            GateEvent(event="close", event_id="evt-api-2", gate_id="CAMT_EXIT_01", timestamp=timestamp),
        ]
    )
    db_session.commit()

    response = client.get("/api/gate/counts/daily", params={"date": "2026-10-07"})

    assert response.status_code == 200
    assert response.json() == {
        "open_count": 1,
        "close_count": 1,
        "count_gap": 0,
        "has_missing_message": False,
    }


def test_gate_count_uses_bangkok_day_boundary(db_session):
    service = GateService(db_session)
    service.record_event(
        GateEventPayload(
            event="open",
            event_id="evt-boundary",
            gate_id="CAMT_EXIT_01",
            timestamp=datetime(2026, 10, 6, 17, 30, tzinfo=timezone.utc),
        )
    )

    result = service.get_daily_count(datetime(2026, 10, 7))

    assert result["open_count"] == 1


def test_weekly_summary_includes_daily_counts_and_peak_hours(db_session):
    service = GateService(db_session)
    service.record_event(
        GateEventPayload(
            event="open",
            event_id="evt-weekly-open",
            gate_id="CAMT_EXIT_01",
            timestamp=datetime(2026, 10, 6, 2, 15, tzinfo=timezone.utc),
        )
    )
    service.record_event(
        GateEventPayload(
            event="close",
            event_id="evt-weekly-close",
            gate_id="CAMT_EXIT_01",
            timestamp=datetime(2026, 10, 6, 2, 16, tzinfo=timezone.utc),
        )
    )

    result = service.get_weekly_summary(datetime(2026, 10, 7).date())

    assert result["start_date"].isoformat() == "2026-10-05"
    assert result["open_count"] == 1
    assert result["close_count"] == 1
    assert result["daily"][1]["open_count"] == 1
    assert result["peak_hours"]["open"] == {"hour": "09:00", "count": 1}
