"""Feature 6 commuter chatbot (UTC-13/14/15).

Language detection + keyword intent routing, linear fill-rate ETA with the
full-lot trend fallback, and the Haversine travel-time estimate.
"""

import re
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from schemas.analytics import TrendDataPoint, TrendResponse
from db.models import ParkingSnapshot, ParkingSnapshot2
from services import user_chatbot_service as chatbot_module
from services.user_chatbot_service import ChatbotService


def _snapshot2(lot_id, timestamp, total, occupied, available):
    return ParkingSnapshot2(
        lot_id=lot_id,
        timestamp=timestamp,
        total_spaces=total,
        available_spaces=available,
        occupied_spaces=occupied,
        occupacy_rate=(occupied / total) * 100 if total else 0.0,
        confidence=0.95,
        processing_time_seconds=0.1,
    )


# ---------- UTC-13: language detection ----------

def test_is_thai_detects_thai_and_english_text(db_session):
    service = ChatbotService(db_session)

    assert service.is_thai("มีที่จอดไหม") is True
    assert service.is_thai("any space at CAMT_01?") is False


# ---------- UTC-13: keyword intent routing ----------

def test_thai_availability_question_routes_to_eta_reply(db_session):
    # TC-13-1
    now = datetime.utcnow()
    db_session.add(
        _snapshot2("CAMT_02", now, 34, 20, 14)
    )
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=now,
            available_spaces=20,
            total_spaces=30,
            occupied_spaces=10,
            occupacy_rate=33.3,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    db_session.commit()

    service = ChatbotService(db_session)
    service.agent_api_key = None  # keyword-only path

    reply = service.get_reply("มีที่จอดไหม")

    assert reply["type"] == "text"
    assert "ที่ว่าง" in reply["text"]
    assert "20" in reply["text"]


def test_english_availability_question_routes_to_eta_reply(db_session):
    # TC-13-2
    now = datetime.utcnow()
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=now,
            available_spaces=20,
            total_spaces=30,
            occupied_spaces=10,
            occupacy_rate=33.3,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    db_session.commit()

    service = ChatbotService(db_session)
    service.agent_api_key = None

    reply = service.get_reply("any space at CAMT_01?")

    assert reply["type"] == "text"
    assert "spaces left" in reply["text"]


def test_ambiguous_message_with_agent_key_calls_llm_router(db_session):
    # TC-13-3: no keyword matches, agent key configured -> LLM tool-call decides
    now = datetime.utcnow()
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=now,
            available_spaces=20,
            total_spaces=30,
            occupied_spaces=10,
            occupacy_rate=33.3,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    db_session.commit()

    llm_response = MagicMock()
    llm_response.raise_for_status.return_value = None
    llm_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "check_parking_status",
                                "arguments": '{"lot_id": "CAMT_01"}',
                            }
                        }
                    ]
                }
            }
        ]
    }

    service = ChatbotService(db_session)
    service.agent_api_key = "test-agent-key"

    with patch.object(
        chatbot_module.requests, "post", return_value=llm_response
    ) as mock_post:
        reply = service.get_reply("is it busy right now")

    mock_post.assert_called_once()
    assert reply["type"] == "text"
    assert "20" in reply["text"]


def test_ambiguous_message_without_agent_key_degrades_gracefully(db_session):
    # TC-13-4: keyword-only fallback, clarifying reply, no exception
    service = ChatbotService(db_session)
    service.agent_api_key = None

    reply = service.get_reply("is it busy right now")

    assert reply["type"] == "text"
    assert "parking assistant" in reply["text"]


# ---------- UTC-14: calculate_eta ----------

def test_eta_minutes_to_full_uses_linear_fill_rate(db_session):
    # TC-14-1: occupied_diff=6 over 15 min, 4 slots available
    # expected minutes-to-full = 4 / (6/15) = 10
    now = datetime.utcnow()
    db_session.add_all(
        [
            _snapshot2("CAMT_02", now - timedelta(minutes=16), 34, 24, 10),
            _snapshot2("CAMT_02", now, 34, 30, 4),
        ]
    )
    db_session.commit()

    service = ChatbotService(db_session)
    reply = service.calculate_eta(lot_id="CAMT_02", lang="en")

    assert "full in" in reply
    minutes = int(re.search(r"full in ~(\d+) mins", reply).group(1))
    assert abs(minutes - 10) <= 2  # within ±20%


def test_eta_full_lot_falls_back_to_hourly_trends(db_session):
    # TC-14-2: 0 available, flat occupancy -> next likely free hour from 7-day trends
    now = datetime.utcnow()
    db_session.add_all(
        [
            _snapshot2("CAMT_02", now - timedelta(minutes=16), 34, 34, 0),
            _snapshot2("CAMT_02", now, 34, 34, 0),
        ]
    )
    db_session.commit()

    service = ChatbotService(db_session)

    # A trend hour later than "now" with free capacity, else wrap to fallback
    free_hour = (now.hour + 2) % 24
    trend_hour = free_hour if free_hour > now.hour else now.hour
    service.analytics_service = MagicMock()
    service.analytics_service.get_occupancy_trends.return_value = TrendResponse(
        lot_id="CAMT_02",
        trends=[
            TrendDataPoint(
                time_label=now.strftime(f"%Y-%m-%d {trend_hour:02d}:00"),
                average_occupancy=28.0,
            )
        ],
    )

    reply = service.calculate_eta(lot_id="CAMT_02", lang="en")

    assert "full" in reply.lower()
    if free_hour > now.hour:
        assert f"{trend_hour}:00" in reply
    else:
        # 23:00-ish edge: no later hour today, alternative message, no exception
        assert "alternative parking" in reply


def test_eta_with_single_snapshot_returns_status_without_numeric_eta(db_session):
    # TC-14-3: fewer than two snapshots -> status only, no exception
    now = datetime.utcnow()
    db_session.add(_snapshot2("CAMT_02", now, 34, 20, 14))
    db_session.commit()

    service = ChatbotService(db_session)
    reply = service.calculate_eta(lot_id="CAMT_02", lang="en")

    assert "14 spaces left" in reply
    assert "full in" not in reply


def test_eta_without_any_data_returns_apology(db_session):
    service = ChatbotService(db_session)

    reply = service.calculate_eta(lot_id="CAMT_02", lang="en")

    assert "not available" in reply


# ---------- UTC-15: calculate_travel_eta ----------

def test_travel_eta_near_campus_is_small_positive_value(db_session):
    # TC-15-1
    service = ChatbotService(db_session)
    captured = {}

    def fake_eta(lot_id, lang="th", travel_mins=0):
        captured["travel_mins"] = travel_mins
        return "ok"

    service.calculate_eta = fake_eta
    service.calculate_travel_eta(18.802, 98.951)

    assert captured["travel_mins"] >= 1
    assert captured["travel_mins"] <= 5


def test_travel_eta_far_from_campus_scales_with_distance(db_session):
    # TC-15-2: Bangkok coordinates -> large minute value, no exception
    service = ChatbotService(db_session)
    captured = []

    def fake_eta(lot_id, lang="th", travel_mins=0):
        captured.append(travel_mins)
        return "ok"

    service.calculate_eta = fake_eta
    service.calculate_travel_eta(13.7563, 100.5018)

    assert captured[0] > 100  # ~360 km straight-line
