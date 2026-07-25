"""ParkPilot MCP Server (Feature 2).

Exposes the parking system's operational data as MCP tools so that any
MCP-compatible AI agent can query it. Runs on two transports from a single
set of tool definitions:

    stdio           -> local reference clients such as Claude Desktop
    streamable-http -> mounted at /mcp by main.py, used by the Feature 4 LINE bot
"""

from mcp_server.server import mcp

__all__ = ["mcp"]
