"""MCP client authentication (URS-07) and tool rate limiting (NFR-SEC-002)."""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from mcp_server import security
from mcp_server.server import _extract_bearer

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@pytest.fixture(autouse=True)
def clear_rate_limits():
    security.reset_rate_limits()
    yield
    security.reset_rate_limits()


# ---------- URS-07 bearer token parsing ----------

@pytest.mark.parametrize(
    "header,expected",
    [
        ("Bearer abc123", "abc123"),
        ("bearer abc123", "abc123"),
        ("Basic abc123", None),
        ("Bearer ", None),
        ("abc123", None),
        (None, None),
    ],
)
def test_extract_bearer(header, expected):
    assert _extract_bearer(header) == expected


def test_authorization_rejects_when_no_tokens_configured(monkeypatch):
    # ไม่ตั้งโทเค็นไว้ = ปิดกั้นทุกคำขอ ไม่ใช่เปิดให้ทุกคน
    monkeypatch.delenv("MCP_API_TOKENS", raising=False)

    assert security.is_authorized("anything") is False
    assert security.is_authorized(None) is False


def test_authorization_accepts_configured_token(monkeypatch):
    monkeypatch.setenv("MCP_API_TOKENS", "token-a, token-b")

    assert security.is_authorized("token-a") is True
    assert security.is_authorized("token-b") is True
    assert security.is_authorized("token-c") is False


# ---------- URS-07 enforced over HTTP ----------

def test_http_transport_rejects_missing_token(client, monkeypatch):
    monkeypatch.setenv("MCP_API_TOKENS", "valid-token")

    response = client.post("/mcp/", headers=MCP_HEADERS, json=TOOLS_LIST)

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_http_transport_rejects_wrong_token(client, monkeypatch):
    monkeypatch.setenv("MCP_API_TOKENS", "valid-token")

    response = client.post(
        "/mcp/",
        headers={**MCP_HEADERS, "Authorization": "Bearer wrong-token"},
        json=TOOLS_LIST,
    )

    assert response.status_code == 401


def test_http_transport_accepts_valid_token(client, monkeypatch):
    monkeypatch.setenv("MCP_API_TOKENS", "valid-token")
    headers = {**MCP_HEADERS, "Authorization": "Bearer valid-token"}

    init = client.post(
        "/mcp/",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0"},
            },
        },
    )
    assert init.status_code == 200

    client.post(
        "/mcp/",
        headers=headers,
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    response = client.post("/mcp/", headers=headers, json=TOOLS_LIST)

    assert response.status_code == 200
    body = response.text
    if body.startswith("event:"):
        body = [line[6:] for line in body.splitlines() if line.startswith("data: ")][0]
    assert len(json.loads(body)["result"]["tools"]) == 8


# ---------- NFR-SEC-002 rate limiting ----------

def test_rate_limit_allows_calls_under_the_threshold(monkeypatch):
    monkeypatch.setattr(security, "RATE_LIMIT_PER_MINUTE", 3)

    for _ in range(3):
        security.check_rate_limit("client-under")


def test_rate_limit_blocks_calls_over_the_threshold(monkeypatch):
    monkeypatch.setattr(security, "RATE_LIMIT_PER_MINUTE", 3)

    for _ in range(3):
        security.check_rate_limit("client-over")

    with pytest.raises(ToolError, match="Rate limit exceeded"):
        security.check_rate_limit("client-over")


def test_rate_limit_window_resets_after_sixty_seconds(monkeypatch):
    # TC-12-2: คำขอถัดไปต้องสำเร็จหลังหน้าต่าง 60 วินาทีหมดอายุ
    monkeypatch.setattr(security, "RATE_LIMIT_PER_MINUTE", 2)

    fake_now = {"t": 1000.0}
    monkeypatch.setattr(security.time, "monotonic", lambda: fake_now["t"])

    for _ in range(2):
        security.check_rate_limit("client-reset")

    with pytest.raises(ToolError, match="Rate limit exceeded"):
        security.check_rate_limit("client-reset")

    fake_now["t"] += 61.0
    security.check_rate_limit("client-reset")  # ต้องไม่ raise หลัง window reset


def test_rate_limit_quota_is_per_client(monkeypatch):
    monkeypatch.setattr(security, "RATE_LIMIT_PER_MINUTE", 2)

    for _ in range(2):
        security.check_rate_limit("client-a")

    # โควตาของ client-a หมดแล้ว แต่ client-b ต้องไม่ถูกกระทบ
    security.check_rate_limit("client-b")

    with pytest.raises(ToolError):
        security.check_rate_limit("client-a")


def test_rate_limit_applies_to_tool_invocations(monkeypatch):
    monkeypatch.setattr(security, "RATE_LIMIT_PER_MINUTE", 1)

    @security.rate_limited
    def fake_tool():
        return "ok"

    assert fake_tool() == "ok"
    with pytest.raises(ToolError, match="Rate limit exceeded"):
        fake_tool()


def test_client_context_isolates_rate_limit_identity(monkeypatch):
    monkeypatch.setattr(security, "RATE_LIMIT_PER_MINUTE", 1)

    @security.rate_limited
    def fake_tool():
        return "ok"

    with security.client_context("http:aaaa"):
        assert fake_tool() == "ok"

    # ผู้เรียกคนละรายมีโควตาของตัวเอง
    with security.client_context("http:bbbb"):
        assert fake_tool() == "ok"
