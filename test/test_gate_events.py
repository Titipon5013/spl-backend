import json
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from db.models import GateEvent
from mqtt import handler
from routes.analytics_controller import get_gate_counts


def _deliver_gate_event(db_session, payload):
    def db_generator():
        yield db_session

    message = SimpleNamespace(
        retain=False,
        topic="test/gate",
        payload=json.dumps(payload).encode(),
    )
    with patch.object(handler, "get_db", db_generator):
        handler.on_message(None, None, message)


def test_gate_event_qos_duplicate_is_persisted_once(db_session):
    payload = {
        "event": "open",
        "event_id": "event-001",
        "gate_id": "CAMT_EXIT_01",
        "camera": 3,
        "vehicle_class": "car",
        "confidence": 0.88,
        "timestamp": "2026-10-07T12:41:03.512+07:00",
    }

    _deliver_gate_event(db_session, payload)
    _deliver_gate_event(db_session, payload)

    events = db_session.query(GateEvent).all()
    assert len(events) == 1
    assert events[0].event_id == "event-001"
    assert events[0].gate_id == "CAMT_EXIT_01"
    assert events[0].vehicle_class == "car"
    assert events[0].confidence == 0.88


def test_gate_count_endpoint_aggregates_persisted_events_by_hour(db_session):
    db_session.add_all([
        GateEvent(
            event="open", event_id="open-1", gate_id="CAMT_EXIT_01",
            timestamp=datetime.fromisoformat("2026-10-07T12:00:00+07:00"),
        ),
        GateEvent(
            event="close", event_id="close-1", gate_id="CAMT_EXIT_01",
            timestamp=datetime.fromisoformat("2026-10-07T12:00:01+07:00"),
        ),
        GateEvent(
            event="open", event_id="open-2", gate_id="CAMT_EXIT_01",
            timestamp=datetime.fromisoformat("2026-10-07T13:00:00+07:00"),
        ),
    ])
    db_session.commit()

    result = get_gate_counts(day=date(2026, 10, 7), gate_id="CAMT_EXIT_01", db=db_session)

    assert result["open_count"] == 2
    assert result["close_count"] == 1
    assert result["possible_missing_events"] is False
    assert result["hourly"][12] == {"hour": 12, "open_count": 1, "close_count": 1}
    assert result["hourly"][13] == {"hour": 13, "open_count": 1, "close_count": 0}


def test_gate_count_endpoint_flags_more_than_one_unpaired_event(db_session):
    db_session.add_all([
        GateEvent(
            event="open", event_id=f"open-{index}", gate_id="CAMT_EXIT_01",
            timestamp=datetime.fromisoformat("2026-10-07T12:00:00+07:00"),
        )
        for index in range(3)
    ])
    db_session.commit()

    result = get_gate_counts(day=date(2026, 10, 7), gate_id=None, db=db_session)

    assert result["count_difference"] == 3
    assert result["possible_missing_events"] is True
