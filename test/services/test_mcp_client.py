"""Feature 4 MCP client — tool mapping and transport modes."""

from unittest.mock import MagicMock, patch

import pytest

from services.mcp_client import ADMIN_TOOL_TO_MCP, McpClient, McpClientError, map_admin_tool


def test_admin_tools_map_onto_feature_two_tools():
    assert map_admin_tool("get_parking_status") == "get_live_occupancy"
    assert map_admin_tool("check_device_health") == "get_system_health"
    assert map_admin_tool("get_parking_analytics") == "analyze_occupancy_trends"
    assert map_admin_tool("get_system_anomalies") == "get_system_anomalies"
    assert map_admin_tool("mark_anomaly_reviewed") == "mark_anomaly_reviewed"
    assert set(ADMIN_TOOL_TO_MCP.values()).issubset(
        {
            "get_live_occupancy",
            "check_slot_status",
            "find_available_slots",
            "analyze_occupancy_trends",
            "get_dwell_time_stats",
            "get_system_anomalies",
            "mark_anomaly_reviewed",
            "get_system_health",
        }
    )


def test_unknown_admin_tool_raises():
    with pytest.raises(McpClientError, match="Unknown admin tool"):
        map_admin_tool("get_hotel_revenue")


def test_http_mode_requires_bearer_token():
    client = McpClient(token="", mode="http")
    with pytest.raises(McpClientError, match="MCP_LINE_BOT_TOKEN"):
        client.call_tool("get_parking_status", {"lot_id": "CAMT_01"})


def test_inprocess_mode_calls_fastmcp_dispatcher(db_session):
    from datetime import datetime

    from db.models import ParkingSnapshot

    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=datetime.utcnow(),
            available_spaces=7,
            total_spaces=30,
            occupied_spaces=23,
            occupacy_rate=76.67,
            confidence=0.95,
            processing_time_seconds=0.4,
        )
    )
    db_session.commit()

    client = McpClient(mode="inprocess")
    result = client.call_tool("get_parking_status", {"lot_id": "CAMT_01"})

    assert result["occupied_spaces"] == 23
    assert result["available_spaces"] == 7


def test_http_mode_passes_authorization_header(monkeypatch):
    captured = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            return None

        async def call_tool(self, name, arguments):
            block = MagicMock()
            block.text = '{"ok": true, "tool": "%s"}' % name
            result = MagicMock()
            result.isError = False
            result.content = [block]
            return result

    class FakeTransport:
        async def __aenter__(self):
            return (MagicMock(), MagicMock(), lambda: None)

        async def __aexit__(self, *args):
            return False

    def fake_streamablehttp_client(url, headers=None, timeout=30):
        captured["url"] = url
        captured["headers"] = headers
        return FakeTransport()

    monkeypatch.setattr(
        "mcp.client.streamable_http.streamablehttp_client",
        fake_streamablehttp_client,
    )
    monkeypatch.setattr("mcp.ClientSession", lambda *a, **k: FakeSession())

    client = McpClient(
        token="line-bot-token",
        base_url="http://127.0.0.1:8000/mcp/",
        mode="http",
    )
    result = client.call_tool("get_parking_status", {"lot_id": "CAMT_01"})

    assert captured["headers"]["Authorization"] == "Bearer line-bot-token"
    assert captured["url"] == "http://127.0.0.1:8000/mcp/"
    assert result["ok"] is True
    assert result["tool"] == "get_live_occupancy"
