"""Client authentication (URS-07) and tool-invocation rate limiting (NFR-SEC-002)."""

import os
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

from mcp.server.fastmcp.exceptions import ToolError

# ผู้เรียกของ request ปัจจุบัน middleware เป็นคนตั้งค่านี้
# ถ้าเป็นการรันแบบ stdio (เครื่อง local) จะใช้ค่า default
_STDIO_CLIENT = "stdio-local"
current_client: ContextVar[str] = ContextVar("current_client", default=_STDIO_CLIENT)

RATE_LIMIT_PER_MINUTE = int(os.getenv("MCP_RATE_LIMIT_PER_MINUTE", "60"))
_WINDOW_SECONDS = 60

_invocations: dict[str, deque] = defaultdict(deque)


def get_configured_tokens() -> set[str]:
    """โทเค็นที่อนุญาต อ่านจาก MCP_API_TOKENS (คั่นด้วยจุลภาค)"""
    raw = os.getenv("MCP_API_TOKENS", "")
    return {token.strip() for token in raw.split(",") if token.strip()}


def is_authorized(token: str | None) -> bool:
    configured = get_configured_tokens()
    if not configured:
        # ไม่ได้ตั้งโทเค็นไว้ = ปิดกั้นทุกคำขอผ่าน HTTP
        # ป้องกันการเผลอเปิด /mcp ทิ้งไว้โดยไม่มีการยืนยันตัวตน
        return False
    return token in configured


@contextmanager
def client_context(client_id: str):
    token = current_client.set(client_id)
    try:
        yield
    finally:
        current_client.reset(token)


def check_rate_limit(client_id: str) -> None:
    """Sliding window ต่อผู้เรียกหนึ่งราย"""
    now = time.monotonic()
    history = _invocations[client_id]

    while history and now - history[0] >= _WINDOW_SECONDS:
        history.popleft()

    if len(history) >= RATE_LIMIT_PER_MINUTE:
        retry_after = int(_WINDOW_SECONDS - (now - history[0])) + 1
        raise ToolError(
            f"Rate limit exceeded: {RATE_LIMIT_PER_MINUTE} tool invocations per minute. "
            f"Retry in {retry_after}s."
        )

    history.append(now)


def rate_limited(func):
    """ครอบ tool ทุกตัว ให้ถูกจำกัดอัตราการเรียกทั้งสอง transport"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        check_rate_limit(current_client.get())
        return func(*args, **kwargs)

    return wrapper


def reset_rate_limits() -> None:
    """ใช้ในเทสต์เท่านั้น"""
    _invocations.clear()
