from datetime import datetime
from unittest.mock import patch

import pytest
from db.models import Admin
from enums import ApprovalStatus, AuthProvider, RoleEnum


@pytest.fixture
def approved_admin(db_session):
    admin = Admin(
        username="superadmin",
        email="admin@example.com",
        hashed_password="hashed",
        role=RoleEnum.admin,
        auth_provider=AuthProvider.local,
        approval_status=ApprovalStatus.approved,
        created_at=datetime.utcnow(),
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture
def pending_oauth_admin(db_session):
    admin = Admin(
        username="newuser",
        email="newuser@gmail.com",
        role=RoleEnum.operator,
        auth_provider=AuthProvider.google,
        approval_status=ApprovalStatus.pending,
        oauth_sub="google-sub-123",
        created_at=datetime.utcnow(),
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def _auth_headers(admin_id: int):
    from auth.dependencies import create_access_token

    token = create_access_token({"user_id": admin_id, "role": RoleEnum.admin.value})
    return {"Authorization": f"Bearer {token}"}


def test_list_admin_access_requests(client, approved_admin, pending_oauth_admin):
    response = client.get(
        "/api/admin-access/requests",
        headers=_auth_headers(approved_admin.id),
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["email"] == "newuser@gmail.com"


@patch("services.admin_access_service.EmailService.send_line_qr_email", return_value=True)
def test_approve_admin_access_request(
    mock_email, client, approved_admin, pending_oauth_admin
):
    response = client.put(
        f"/api/admin-access/requests/{pending_oauth_admin.id}",
        json={"status": "approved"},
        headers=_auth_headers(approved_admin.id),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    mock_email.assert_called_once_with(
        pending_oauth_admin.email,
        pending_oauth_admin.username,
    )
