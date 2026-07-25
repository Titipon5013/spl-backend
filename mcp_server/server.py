"""FastMCP instance and the authenticated HTTP transport wrapper."""

import os
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from mcp_server.security import client_context, is_authorized
from mcp_server.tools import register_tools

# Host ที่อนุญาตให้เรียก /mcp ได้ ป้องกัน DNS rebinding
# ต้องเพิ่ม host ของเซิร์ฟเวอร์ CAMT ตอน deploy ผ่าน MCP_ALLOWED_HOSTS
_DEFAULT_ALLOWED_HOSTS = "localhost,localhost:8000,127.0.0.1,127.0.0.1:8000"


def _allowed_hosts() -> list[str]:
    raw = os.getenv("MCP_ALLOWED_HOSTS", _DEFAULT_ALLOWED_HOSTS)
    return [host.strip() for host in raw.split(",") if host.strip()]

INSTRUCTIONS = """\
ParkPilot exposes the CAMT campus parking system's live and historical data.

Lot IDs are "CAMT_01" and "CAMT_02". For questions about right now use
get_live_occupancy, check_slot_status or find_available_slots. For questions
about patterns over time use analyze_occupancy_trends or get_dwell_time_stats.
For hardware and pipeline problems use get_system_health and
get_system_anomalies, then mark_anomaly_reviewed once an administrator has
handled the issue.

Timestamps are UTC and dates are ISO 8601.\
"""

mcp = FastMCP(
    name="parkpilot",
    instructions=INSTRUCTIONS,
    # stateless ทำให้ mount รวมกับ FastAPI ได้โดยไม่ต้องจัดการ session ข้าม request
    stateless_http=True,
    # main.py mount แอปนี้ไว้ที่ /mcp อยู่แล้ว ถ้าปล่อย default ("/mcp")
    # เส้นทางจริงจะกลายเป็น /mcp/mcp
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(allowed_hosts=_allowed_hosts()),
)

register_tools(mcp)


def _extract_bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


_active_app = None


def _build_transport_app():
    """สร้าง session manager และ ASGI app ชุดใหม่

    SDK อนุญาตให้เรียก session_manager.run() ได้ครั้งเดียวต่อหนึ่ง instance
    ดังนั้นทุกครั้งที่แอปเริ่มทำงานใหม่ ต้องสร้าง session manager ใหม่ด้วย
    ไม่งั้นการ start รอบที่สองในโปรเซสเดิมจะพัง (เช่น ตอนรันเทสต์)

    _session_manager เป็น attribute ภายในของ FastMCP ตรงนี้คือจุดเดียว
    ที่แตะมัน ถ้า SDK เปลี่ยนโครงสร้างให้แก้ที่นี่ที่เดียว
    """
    mcp._session_manager = None
    inner = mcp.streamable_http_app()

    async def authenticated_app(scope, receive, send):
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        token = _extract_bearer(headers.get("authorization"))

        if not is_authorized(token):
            response = JSONResponse(
                {
                    "error": "unauthorized",
                    "detail": "A valid bearer token is required to invoke ParkPilot MCP tools.",
                },
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        # แยกโควตา rate limit ตามโทเค็นของผู้เรียกแต่ละราย
        with client_context(f"http:{token[:8]}"):
            await inner(scope, receive, send)

    return authenticated_app


def create_http_app():
    """ASGI app ที่ main.py เอาไป mount ที่ /mcp

    ตัวนี้เป็นแค่ตัวส่งต่อที่ "อยู่นิ่ง" เพราะ FastAPI จะจำ object ที่ mount ไว้
    ตั้งแต่ตอน import ส่วนแอปจริงข้างในถูกสร้างใหม่ทุกครั้งใน mcp_lifespan
    """

    async def dispatcher(scope, receive, send):
        if _active_app is None:
            response = JSONResponse(
                {
                    "error": "unavailable",
                    "detail": "The MCP transport is not running.",
                },
                status_code=503,
            )
            await response(scope, receive, send)
            return
        await _active_app(scope, receive, send)

    return dispatcher


@asynccontextmanager
async def mcp_lifespan():
    """ต้องผูกเข้ากับ lifespan ของ FastAPI

    แอปที่ถูก mount จะไม่ได้รับ lifespan ของตัวเองโดยอัตโนมัติ
    ถ้าไม่เรียกอันนี้ session manager จะไม่ทำงาน และ /mcp จะตอบ error ทุกครั้ง
    """
    global _active_app
    _active_app = _build_transport_app()
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        _active_app = None


def http_transport_enabled() -> bool:
    return os.getenv("MCP_HTTP_ENABLED", "true").lower() not in ("false", "0", "no")
