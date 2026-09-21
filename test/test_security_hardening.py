"""Regression tests for the security fixes applied after the audit run-1.

Each test asserts the hardened invariant so the original defect cannot silently
return.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from db.models import Admin, LicensePlateRequest
from enums import ApprovalStatus, RequestStatus, RoleEnum
from schemas.admin import AdminOut, AdminUpdate
from schemas.request import RequestStatusUpdate
from services.admin_service import AdminService
from services.plate_request_service import PlateRequestService


def _admin_out(admin_id=1, role=RoleEnum.admin, approval=ApprovalStatus.approved):
    return AdminOut(
        id=admin_id,
        username="u",
        email=f"u{admin_id}@example.com",
        hashed_password="",
        role=role,
        approval_status=approval,
        auth_provider="local",
    )


# --- Admin role self-escalation -------------------------------------------------

def test_operator_cannot_change_own_role():
    repo = MagicMock()
    repo.get_admin_by_id.return_value = Admin(id=1, role=RoleEnum.operator, hashed_password="")
    svc = AdminService(repo)

    with pytest.raises(HTTPException) as exc:
        svc.update_admin(1, AdminUpdate(role=RoleEnum.admin), _admin_out(1, RoleEnum.operator))
    assert exc.value.status_code == 403
    repo.update_admin.assert_not_called()


def test_operator_cannot_change_another_admins_role():
    repo = MagicMock()
    repo.get_admin_by_id.return_value = Admin(id=2, role=RoleEnum.admin, hashed_password="")
    svc = AdminService(repo)

    with pytest.raises(HTTPException) as exc:
        svc.update_admin(2, AdminUpdate(role=RoleEnum.admin), _admin_out(1, RoleEnum.operator))
    assert exc.value.status_code == 403
    repo.update_admin.assert_not_called()


def test_admin_can_change_another_admins_role():
    repo = MagicMock()
    repo.get_admin_by_id.return_value = Admin(id=2, role=RoleEnum.operator, hashed_password="")
    repo.update_admin.return_value = Admin(
        id=2, username="x", email="x@example.com", role=RoleEnum.admin,
        hashed_password="", approval_status=ApprovalStatus.approved, auth_provider="local",
    )
    svc = AdminService(repo)

    svc.update_admin(2, AdminUpdate(role=RoleEnum.admin), _admin_out(1, RoleEnum.admin))
    repo.update_admin.assert_called_once()


# --- Unauthenticated routes -----------------------------------------------------

def test_gate_open_requires_auth(client):
    with patch("services.parking_service.requests.get") as edge:
        response = client.get("/api/parking/open")
    assert response.status_code == 401
    edge.assert_not_called()


def test_gate_open_allows_authenticated_admin(client):
    from main import app
    from auth import dependencies

    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: _admin_out()
    try:
        with patch("services.parking_service.requests.get") as edge:
            edge.return_value = MagicMock(status_code=200, json=lambda: {"status": "opened"})
            response = client.get("/api/parking/open")
        assert response.status_code == 200
        assert edge.call_count == 1
    finally:
        app.dependency_overrides.pop(dependencies.get_current_admin_user, None)


def test_entry_records_list_requires_auth(client):
    assert client.get("/api/entry-records").status_code == 401


# --- S3 key generation ----------------------------------------------------------

def test_s3_upload_uses_server_generated_key():
    from helpers import s3_cloudfront as mod

    captured = {}
    fake_client = MagicMock()
    fake_client.upload_fileobj.side_effect = lambda f, b, key, **kw: captured.update(key=key, extra=kw)

    with patch.object(mod.boto3, "client", return_value=fake_client):
        s3 = mod.S3CloudFront("a", "b", "us-east-1", "bucket", "https://cdn.example.com")
        url = s3.upload_file(MagicMock(), "../../evil-name.jpg", prefix="plates/")

    assert captured["key"] != "../../evil-name.jpg"
    assert captured["key"].startswith("plates/")
    assert captured["key"].endswith(".jpg")
    assert "evil" not in captured["key"]
    assert url == f"https://cdn.example.com/{captured['key']}"
    assert captured["extra"]["ExtraArgs"]["ContentDisposition"] == "attachment"


# --- Report trigger role check --------------------------------------------------

def test_report_trigger_requires_admin_role(client):
    from main import app
    from auth import dependencies

    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: _admin_out(
        1, RoleEnum.operator
    )
    try:
        assert client.post("/api/reports/trigger").status_code == 403
    finally:
        app.dependency_overrides.pop(dependencies.get_current_admin_user, None)


# --- MCP range bound ------------------------------------------------------------

def test_mcp_range_is_bounded(monkeypatch):
    from mcp_server.tools import _resolve_range
    from mcp.server.fastmcp.exceptions import ToolError

    monkeypatch.setenv("MCP_MAX_RANGE_DAYS", "366")
    with pytest.raises(ToolError):
        _resolve_range("0001-01-01", "9999-12-31")
    start, end = _resolve_range("2026-01-01", "2026-02-01")
    assert (end - start).days == 31


# --- Login rate limit -----------------------------------------------------------

def test_login_rate_limit_blocks_burst(monkeypatch, client, db_session):
    from helpers import rate_limit

    monkeypatch.setenv("LOGIN_RATE_LIMIT_PER_MINUTE", "3")
    rate_limit.reset_login_rate_limits()
    try:
        statuses = [
            client.post(
                "/api/login", data={"username": "nobody@example.com", "password": "x"}
            ).status_code
            for _ in range(5)
        ]
        assert 429 in statuses
    finally:
        rate_limit.reset_login_rate_limits()


# --- Plate request state machine ------------------------------------------------

def test_plate_request_reapproval_is_rejected():
    repo = MagicMock()
    repo.get_request_by_id.return_value = LicensePlateRequest(
        id=1, plate_number="ABC-123", user_id=1, plate_image_url="u",
        status=RequestStatus.approved,
    )
    svc = PlateRequestService(repo)

    with pytest.raises(HTTPException) as exc:
        svc.update_plate_status(1, RequestStatusUpdate(status=RequestStatus.approved), _admin_out())
    assert exc.value.status_code == 409
    repo.add_plate.assert_not_called()


def test_plate_request_duplicate_plate_is_rejected():
    repo = MagicMock()
    repo.get_request_by_id.return_value = LicensePlateRequest(
        id=1, plate_number="ABC-123", user_id=1, plate_image_url="u",
        status=RequestStatus.pending,
    )
    repo.get_plate_by_number.return_value = object()
    svc = PlateRequestService(repo)

    with pytest.raises(HTTPException) as exc:
        svc.update_plate_status(1, RequestStatusUpdate(status=RequestStatus.approved), _admin_out())
    assert exc.value.status_code == 409
    repo.add_plate.assert_not_called()
