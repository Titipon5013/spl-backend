"""Feature 4 MCP client — invokes Feature 2 tools for the admin LINE bot.

Production path: HTTP streamable transport at MCP_INTERNAL_URL with a bearer
token from MCP_LINE_BOT_TOKEN (must also appear in MCP_API_TOKENS).

Test / local fallback: MCP_INTERNAL_MODE=inprocess calls the FastMCP dispatcher
in-process so unit tests do not need a live HTTP server.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

ADMIN_TOOL_TO_MCP = {
    "get_parking_status": "get_live_occupancy",
    "check_device_health": "get_system_health",
    "get_parking_analytics": "analyze_occupancy_trends",
    "get_system_anomalies": "get_system_anomalies",
    "mark_anomaly_reviewed": "mark_anomaly_reviewed",
    "find_available_slots": "find_available_slots",
    "check_slot_status": "check_slot_status",
    "get_dwell_time_stats": "get_dwell_time_stats",
    "get_live_occupancy": "get_live_occupancy",
    "get_system_health": "get_system_health",
    "analyze_occupancy_trends": "analyze_occupancy_trends",
}


class McpClientError(RuntimeError):
    """Raised when an MCP tool call fails or returns an error payload."""


def map_admin_tool(name: str) -> str:
    """Map an admin-bot LLM tool name onto a Feature 2 MCP tool name."""
    mapped = ADMIN_TOOL_TO_MCP.get(name)
    if mapped is None:
        raise McpClientError(f"Unknown admin tool '{name}'.")
    return mapped


class McpClient:
    """Thin wrapper used by AdminChatbotService to reach Feature 2 tools."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        mode: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.token = token if token is not None else os.getenv("MCP_LINE_BOT_TOKEN", "")
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv("MCP_INTERNAL_URL", "http://127.0.0.1:8000/mcp/")
        )
        self.mode = (
            mode
            if mode is not None
            else os.getenv("MCP_INTERNAL_MODE", "http")
        ).lower()
        self.timeout = timeout

    async def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> dict:
        mcp_name = map_admin_tool(name)
        args = arguments or {}
        if self.mode == "inprocess":
            return await self._call_inprocess(mcp_name, args)
        return await self._call_http(mcp_name, args)

    async def _call_inprocess(self, name: str, arguments: dict[str, Any]) -> dict:
        from mcp_server.server import mcp

        try:
            result = await mcp.call_tool(name, arguments)
            if isinstance(result, tuple):
                result = result[0]
            if not result:
                raise McpClientError(f"MCP tool '{name}' returned empty content.")
            text = result[0].text
            return json.loads(text)
        except McpClientError:
            raise
        except Exception as exc:
            # FastMCP raises ToolError for validation / domain errors
            raise McpClientError(str(exc)) from exc

    async def _call_http(self, name: str, arguments: dict[str, Any]) -> dict:
        if not self.token:
            raise McpClientError(
                "MCP_LINE_BOT_TOKEN is not configured. "
                "Add it to .env and include the same value in MCP_API_TOKENS."
            )

        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            async with streamablehttp_client(
                self.base_url,
                headers=headers,
                timeout=self.timeout,
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)

                    # เช็ค error แบบปลอดภัย
                    if getattr(result, "isError", False):
                        parts = []
                        for block in result.content or []:
                            text = getattr(block, "text", None)
                            if text:
                                parts.append(text)
                        raise McpClientError(
                            "; ".join(parts) or f"MCP tool '{name}' returned an error."
                        )
                    if not result.content:
                        raise McpClientError(f"MCP tool '{name}' returned empty content.")

                    text = result.content[0].text
                    try:
                        return json.loads(text)
                    except (TypeError, json.JSONDecodeError):
                        return {"result": text}
        except McpClientError:
            raise
        except Exception as exc:
            raise McpClientError(f"MCP HTTP call failed: {exc}") from exc