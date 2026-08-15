"""Feature 4 admin chatbot — linked gate + MCP tool execution."""

from datetime import datetime
from unittest.mock import MagicMock, patch

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

    reply = service.get_reply("Ustranger", "สถานะลานจอดตอนนี้")

    assert "/link" in reply["text"]
    mcp.call_tool.assert_not_called()


def test_execute_tool_goes_through_mcp_client(db_session):
    _link(db_session)
    mcp = MagicMock()
    mcp.call_tool.return_value = {
        "lot_id": "CAMT_01",
        "occupied_spaces": 10,
        "available_spaces": 20,
    }
    service = AdminChatbotService(db_session, mcp_client=mcp)

    raw = service._execute_tool("get_parking_status", {"lot_id": "CAMT_01"})

    mcp.call_tool.assert_called_once_with(
        "get_parking_status", {"lot_id": "CAMT_01"}
    )
    assert "occupied_spaces" in raw


def test_execute_tool_returns_error_json_on_mcp_failure(db_session):
    mcp = MagicMock()
    mcp.call_tool.side_effect = McpClientError("boom")
    service = AdminChatbotService(db_session, mcp_client=mcp)

    raw = service._execute_tool("get_parking_status", {"lot_id": "CAMT_01"})

    assert "boom" in raw


def test_linked_admin_without_api_key_gets_ready_error(db_session, monkeypatch):
    _link(db_session)
    monkeypatch.delenv("CLOUD_API_KEY", raising=False)
    service = AdminChatbotService(db_session, mcp_client=MagicMock())

    reply = service.get_reply("Uadmin1", "how full is the lot?")

    assert "API Key" in reply["text"]


def test_linked_admin_llm_tool_call_uses_mcp(db_session, monkeypatch):
    _link(db_session)
    monkeypatch.setenv("CLOUD_API_KEY", "test-key")

    mcp = MagicMock()
    mcp.call_tool.return_value = {"occupied_spaces": 5, "available_spaces": 25}

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
    ):
        service = AdminChatbotService(db_session, mcp_client=mcp)
        reply = service.get_reply("Uadmin1", "how full?")

    assert reply["text"] == "5 cars parked."
    mcp.call_tool.assert_called_once()
