"""Feature 2 MCP tool tests (URS-08 to URS-15).

Tools are invoked through the FastMCP dispatcher rather than by calling the
Python functions directly, so these tests also cover schema validation and the
error contract an AI agent would actually see.
"""

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from db.models import DeviceHealth, ParkingEventLog, ParkingSnapshot
from mcp_server.security import reset_rate_limits
from mcp_server.server import mcp
from services.anomaly_service import AnomalyService


@pytest.fixture(autouse=True)
def clear_rate_limits():
    reset_rate_limits()
    yield
    reset_rate_limits()


def call(name: str, **arguments):
    """เรียก tool ผ่าน FastMCP แล้วแกะผลลัพธ์ออกมาเป็น dict

    FastMCP ส่งผลลัพธ์กลับมาเป็น content block ที่เป็น JSON text
    ซึ่งเป็นสิ่งเดียวกับที่ AI agent ฝั่งผู้เรียกจะได้รับ
    """
    result = asyncio.run(mcp.call_tool(name, arguments))
    if isinstance(result, tuple):
        result = result[0]
    return json.loads(result[0].text)


def _snapshot(db, occupied=23, available=7):
    db.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=datetime.utcnow(),
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


# ---------- URS-15 tool surface ----------

def test_all_feature_two_tools_are_registered():
    tools = {tool.name for tool in asyncio.run(mcp.list_tools())}

    assert tools == {
        "get_live_occupancy",
        "check_slot_status",
        "find_available_slots",
        "analyze_occupancy_trends",
        "get_dwell_time_stats",
        "get_system_anomalies",
        "mark_anomaly_reviewed",
        "get_system_health",
    }


def test_every_tool_has_a_description_and_typed_schema():
    for tool in asyncio.run(mcp.list_tools()):
        assert tool.description, f"{tool.name} is missing a description"
        assert tool.inputSchema["type"] == "object"


# ---------- URS-08 ----------

def test_get_live_occupancy_returns_snapshot(db_session):
    _snapshot(db_session)

    result = call("get_live_occupancy", lot_id="CAMT_01")

    assert result["occupied_spaces"] == 23
    assert result["available_spaces"] == 7


def test_get_live_occupancy_errors_when_pipeline_has_no_data(db_session):
    with pytest.raises(ToolError, match="No occupancy data"):
        call("get_live_occupancy", lot_id="CAMT_01")


def test_unknown_lot_is_rejected_with_valid_values(db_session):
    with pytest.raises(ToolError, match="CAMT_01"):
        call("get_live_occupancy", lot_id="MARS_01")


# ---------- URS-09 ----------

def test_check_slot_status_returns_current_state(db_session):
    _event(db_session, "A1", True, minutes_ago=10)

    result = call("check_slot_status", spot_id="A1")

    assert result["state"] == "occupied"
    assert result["spot_id"] == "A1"


def test_check_slot_status_errors_for_unknown_slot(db_session):
    _event(db_session, "A1", True)

    with pytest.raises(ToolError, match="not known"):
        call("check_slot_status", spot_id="ZZ9")


# ---------- URS-12 ----------

def test_find_available_slots_lists_free_spots(db_session):
    _event(db_session, "A1", True)
    _event(db_session, "A2", False)

    result = call("find_available_slots", lot_id="CAMT_01")

    assert result["available_spots"] == ["A2"]
    assert result["available_count"] == 1


# ---------- URS-10 / URS-11 ----------

def test_analyze_occupancy_trends_defaults_to_last_seven_days(db_session):
    _snapshot(db_session)

    result = call("analyze_occupancy_trends", lot_id="CAMT_01")

    assert result["lot_id"] == "CAMT_01"
    assert len(result["trends"]) == 1


def test_analyze_occupancy_trends_rejects_bad_date_format(db_session):
    with pytest.raises(ToolError, match="ISO 8601"):
        call("analyze_occupancy_trends", start_date="last tuesday")


def test_analyze_occupancy_trends_rejects_inverted_range(db_session):
    with pytest.raises(ToolError, match="must be earlier"):
        call(
            "analyze_occupancy_trends",
            start_date="2026-07-25",
            end_date="2026-07-18",
        )


def test_get_dwell_time_stats_returns_kpis_and_period(db_session):
    _snapshot(db_session)
    _event(db_session, "A1", True, minutes_ago=120)
    _event(db_session, "A1", False, minutes_ago=60)

    result = call("get_dwell_time_stats", lot_id="CAMT_01")

    assert result["avg_dwell_time_minutes"] == pytest.approx(60, abs=1)
    assert "period_start" in result and "period_end" in result


# ---------- URS-13 / URS-14 ----------

def test_get_system_anomalies_returns_detected_anomalies(db_session):
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    AnomalyService(db_session).detect_anomalies()

    result = call("get_system_anomalies")

    assert result["count"] >= 1
    assert any(a["anomaly_type"] == "stuck_slot" for a in result["anomalies"])


def test_get_system_anomalies_rejects_unknown_type(db_session):
    with pytest.raises(ToolError, match="Unknown anomaly_type"):
        call("get_system_anomalies", anomaly_type="ghost_car")


def test_mark_anomaly_reviewed_updates_the_record(db_session):
    _event(db_session, "A1", True, minutes_ago=20 * 60)
    AnomalyService(db_session).detect_anomalies()
    anomaly_id = call("get_system_anomalies", anomaly_type="stuck_slot")["anomalies"][0]["anomaly_id"]

    reviewed = call(
        "mark_anomaly_reviewed",
        anomaly_id=anomaly_id,
        reviewed_by="admin@camt.cmu.ac.th",
    )

    assert reviewed["reviewed_by"] == "admin@camt.cmu.ac.th"
    # ตรวจสอบแล้วต้องหายไปจากรายการเริ่มต้น
    assert call("get_system_anomalies", anomaly_type="stuck_slot")["count"] == 0


def test_mark_anomaly_reviewed_errors_for_unknown_id(db_session):
    with pytest.raises(ToolError, match="No anomaly found"):
        call("mark_anomaly_reviewed", anomaly_id=4242, reviewed_by="admin@camt.cmu.ac.th")


# ---------- system health ----------

def test_get_system_health_reports_offline_board(db_session):
    db_session.add(
        DeviceHealth(
            device_id="orange_pi_main",
            device_type="board",
            status="online",
            last_seen=datetime.utcnow() - timedelta(minutes=30),
        )
    )
    db_session.commit()

    result = call("get_system_health", lot_id="CAMT_01")

    assert result["system_status"] == "Critical"
    assert result["board"]["status"] == "offline"
