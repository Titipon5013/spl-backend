"""Feature 4 admin chatbot — linked gate + MCP tool execution."""

import asyncio
import requests
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from db.models import AdminAlertSubscription
from services.admin_chatbot_service import AdminChatbotService
from services.mcp_client import McpClientError


def _link(db, line_user_id="Uadmin1"):
    sub = AdminAlertSubscription(
        line_user_id=line_user_id,
        alert_types="device_offline",
        muted=False,
        linked_at=datetime.utcnow(),
    )
    db.add(sub)
    db.commit()
    return sub


def test_unlinked_admin_gets_link_instructions_without_mcp(db_session):
    mcp = MagicMock()
    service = AdminChatbotService(db_session, mcp_client=mcp)

    reply = asyncio.run(service.get_reply("Ustranger", "สถานะลานจอดตอนนี้"))

    assert "/link" in reply["text"]
    mcp.call_tool.assert_not_called()


def test_execute_tool_goes_through_mcp_client(db_session):
    _link(db_session)
    mcp = MagicMock()
    mcp.call_tool = AsyncMock(return_value={
        "lot_id": "CAMT_01",
        "occupied_spaces": 10,
        "available_spaces": 20,
    })
    service = AdminChatbotService(db_session, mcp_client=mcp)

    raw = asyncio.run(
        service._execute_tool("get_parking_status", {"lot_id": "CAMT_01"})
    )

    mcp.call_tool.assert_called_once_with(
        "get_parking_status", {"lot_id": "CAMT_01"}
    )
    assert "occupied_spaces" in raw


def test_execute_tool_returns_error_json_on_mcp_failure(db_session):
    mcp = MagicMock()
    mcp.call_tool = AsyncMock(side_effect=McpClientError("boom"))
    service = AdminChatbotService(db_session, mcp_client=mcp)

    raw = asyncio.run(
        service._execute_tool("get_parking_status", {"lot_id": "CAMT_01"})
    )

    assert "boom" in raw


def test_admin_llm_schema_exposes_exactly_seven_mapped_tools(db_session):
    service = AdminChatbotService(db_session, mcp_client=MagicMock())
    names = {
        tool["function"]["name"] for tool in service._get_admin_tools_schema()
    }

    assert names == {
        "get_parking_status",
        "check_device_health",
        "get_parking_analytics",
        "get_system_anomalies",
        "mark_anomaly_reviewed",
        "find_available_slots",
        "check_slot_status",
    }


def test_linked_admin_without_api_key_gets_ready_error(db_session, monkeypatch):
    _link(db_session)
    monkeypatch.delenv("CLOUD_API_KEY", raising=False)
    service = AdminChatbotService(db_session, mcp_client=MagicMock())

    reply = asyncio.run(service.get_reply("Uadmin1", "how full is the lot?"))

    assert "API Key" in reply["text"]


def test_linked_admin_llm_tool_call_uses_mcp(db_session, monkeypatch):
    _link(db_session)
    monkeypatch.setenv("CLOUD_API_KEY", "test-key")

    mcp = MagicMock()
    mcp.call_tool = AsyncMock(
        return_value={"occupied_spaces": 5, "available_spaces": 25}
    )

    llm_step1 = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "get_parking_status",
                                "arguments": '{"lot_id":"CAMT_01"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    llm_step2 = {
        "choices": [{"message": {"role": "assistant", "content": "5 cars parked."}}]
    }

    mock_response_1 = MagicMock()
    mock_response_1.json.return_value = llm_step1
    mock_response_1.raise_for_status = MagicMock()
    mock_response_2 = MagicMock()
    mock_response_2.json.return_value = llm_step2
    mock_response_2.raise_for_status = MagicMock()

    with patch(
        "services.admin_chatbot_service.requests.post",
        side_effect=[mock_response_1, mock_response_2],
    ) as post:
        service = AdminChatbotService(db_session, mcp_client=mcp)
        reply = asyncio.run(service.get_reply("Uadmin1", "how full?"))

    assert reply["text"] == "5 cars parked."
    mcp.call_tool.assert_called_once()
    second_messages = post.call_args_list[1].kwargs["json"]["messages"]
    assert second_messages[-2] == llm_step1["choices"][0]["message"]
    assert second_messages[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "get_parking_status",
        "content": '{"occupied_spaces": 5, "available_spaces": 25}',
    }
    assert service._clean_response_text("การเข้าพัก") == "การเข้าจอด"


def test_linked_admin_llm_timeout_returns_fallback(db_session, monkeypatch):
    _link(db_session)
    monkeypatch.setenv("CLOUD_API_KEY", "test-key")
    mcp = MagicMock()

    with patch(
        "services.admin_chatbot_service.requests.post",
        side_effect=requests.exceptions.Timeout("timed out"),
    ):
        service = AdminChatbotService(db_session, mcp_client=mcp)
        reply = asyncio.run(service.get_reply("Uadmin1", "สถานะลานจอดตอนนี้"))

    assert "ระบบประมวลผลคำถามหรือการเชื่อมต่อขัดข้องชั่วคราวครับ" in reply["text"]
    mcp.call_tool.assert_not_called()


def test_admin_agent_uses_configured_openrouter_model(db_session, monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "vendor/custom-model")
    monkeypatch.delenv("AGENT_ENDPOINT", raising=False)
    service = AdminChatbotService(db_session, mcp_client=MagicMock())

    assert service.endpoint == "https://openrouter.ai/api/v1/chat/completions"
    assert service.model == "vendor/custom-model"


def test_admin_prompt_contains_explicit_utc_timestamp(db_session, monkeypatch):
    _link(db_session)
    monkeypatch.setenv("CLOUD_API_KEY", "test-key")
    captured = {}

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}]
    }

    def capture_post(*args, **kwargs):
        captured["prompt"] = kwargs["json"]["messages"][0]["content"]
        return response

    with patch("services.admin_chatbot_service.requests.post", capture_post):
        service = AdminChatbotService(db_session, mcp_client=MagicMock())
        assert asyncio.run(service.get_reply("Uadmin1", "status"))["text"] == "ok"

    timestamp_text = captured["prompt"].split(
        "[Reference: Current date and time is ", 1
    )[1].rstrip("]")
    timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))

    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() == timedelta(0)


def test_admin_response_cleanup_replaces_hotel_terms(db_session):
    """SRS-55: only parking terminology may remain in cleaned output."""
    service = AdminChatbotService(db_session, mcp_client=MagicMock())

    cleaned = service._clean_response_text("อัตราการเข้าพัก และ ผู้เข้าพัก เข้าพัก")

    assert "เข้าพัก" not in cleaned
    assert "อัตราการเข้าจอด" in cleaned


def test_two_llm_calls_share_deadline_and_fallback_when_exhausted(
    db_session, monkeypatch
):
    _link(db_session)
    monkeypatch.setenv("CLOUD_API_KEY", "test-key")

    tool_call_response = MagicMock()
    tool_call_response.raise_for_status.return_value = None
    tool_call_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "get_parking_status",
                                "arguments": '{"lot_id":"CAMT_01"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    final_response = MagicMock()
    final_response.raise_for_status.return_value = None
    final_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "done"}}]
    }

    clock = {"now": 100.0}
    timeouts = []

    def advancing_post(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        if len(timeouts) == 1:
            clock["now"] = 106.0
            return tool_call_response
        return final_response

    monkeypatch.setattr(
        "services.admin_chatbot_service.time.monotonic", lambda: clock["now"]
    )
    mcp = MagicMock()
    mcp.call_tool = AsyncMock(return_value={"available_spaces": 7})
    with patch("services.admin_chatbot_service.requests.post", advancing_post):
        service = AdminChatbotService(db_session, mcp_client=mcp)
        assert asyncio.run(service.get_reply("Uadmin1", "status"))["text"] == "done"

    assert timeouts == [15.0, 9.0]

    clock["now"] = 200.0
    exhausted_timeouts = []

    def exhausting_post(*args, **kwargs):
        exhausted_timeouts.append(kwargs["timeout"])
        clock["now"] = 216.0
        return tool_call_response

    with patch("services.admin_chatbot_service.requests.post", exhausting_post):
        service = AdminChatbotService(db_session, mcp_client=mcp)
        reply = asyncio.run(service.get_reply("Uadmin1", "status"))

    assert exhausted_timeouts == [15.0]
    assert "temporary error" in reply["text"]
