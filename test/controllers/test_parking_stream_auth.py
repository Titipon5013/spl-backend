from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from jose import jwt

from auth.dependencies import create_access_token
from db.models import Admin
from enums import ApprovalStatus, RoleEnum
from main import app
from routes.parking_controller import STREAM_COOKIE_NAME
from services.dependencies import get_parking_service


def _create_admin(db_session, approval=ApprovalStatus.approved):
    admin = Admin(
        username=f"stream-{approval.value}",
        email=f"stream-{approval.value}@example.com",
        hashed_password="hash",
        role=RoleEnum.operator,
        approval_status=approval,
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def _bearer(admin):
    return {"Authorization": f"Bearer {create_access_token({'user_id': admin.id})}"}


def _stream_cookie(client, admin):
    response = client.post("/api/parking/stream-session", headers=_bearer(admin))
    assert response.status_code == 200
    return response.cookies[STREAM_COOKIE_NAME]


@pytest.mark.parametrize("path", ["/api/parking/inference", "/api/parking/inference2"])
def test_inference_requires_approved_account(client, path):
    response = client.get(path)
    assert response.status_code == 401


def test_approved_operator_can_get_inference(client, db_session):
    admin = _create_admin(db_session)
    parking_service = MagicMock()
    parking_service.infer_parking1_snapshot.return_value = b"image"
    app.dependency_overrides[get_parking_service] = lambda: parking_service
    try:
        response = client.get("/api/parking/inference", headers=_bearer(admin))
        assert response.status_code == 200
        assert response.content == b"image"
        assert response.headers["cache-control"] == "private, no-store"
        parking_service.infer_parking1_snapshot.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_parking_service, None)


@pytest.mark.parametrize("approval", [ApprovalStatus.pending, ApprovalStatus.rejected])
def test_pending_or_revoked_account_cannot_create_stream_session(client, db_session, approval):
    admin = _create_admin(db_session, approval)
    response = client.post("/api/parking/stream-session", headers=_bearer(admin))
    assert response.status_code == 403


def test_approved_account_gets_short_lived_secure_stream_cookie(client, db_session):
    admin = _create_admin(db_session)
    response = client.post("/api/parking/stream-session", headers=_bearer(admin))

    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert f"{STREAM_COOKIE_NAME}=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=none" in cookie
    assert response.headers["cache-control"] == "no-store"

    validation = client.get(
        "/api/parking/stream-auth",
        cookies={STREAM_COOKIE_NAME: response.cookies[STREAM_COOKIE_NAME]},
    )
    assert validation.status_code == 204


def test_approved_operator_can_fetch_stream_through_backend_proxy(client, db_session):
    admin = _create_admin(db_session)
    stream_cookie = _stream_cookie(client, admin)
    upstream = MagicMock()
    upstream.content = b"#EXTM3U"
    upstream.headers = {"content-type": "application/vnd.apple.mpegurl"}

    with patch("routes.parking_controller.requests.get", return_value=upstream):
        response = client.get(
            "/parking/index.m3u8", cookies={STREAM_COOKIE_NAME: stream_cookie}
        )

    assert response.status_code == 200
    assert response.content == b"#EXTM3U"
    assert response.headers["cache-control"] == "no-store"


def test_backend_stream_proxy_rejects_revoked_account(client, db_session):
    admin = _create_admin(db_session)
    stream_cookie = _stream_cookie(client, admin)
    admin.approval_status = ApprovalStatus.revoked
    db_session.commit()

    response = client.get(
        "/parking/index.m3u8", cookies={STREAM_COOKIE_NAME: stream_cookie}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("token", ["not-a-jwt", None])
def test_invalid_or_missing_stream_session_is_unauthorized(client, token):
    cookies = {STREAM_COOKIE_NAME: token} if token else {}
    response = client.get("/api/parking/stream-auth", cookies=cookies)
    assert response.status_code == 401


def test_expired_stream_session_is_unauthorized(client):
    from routes.parking_controller import STREAM_ALGORITHM, STREAM_SECRET_KEY, STREAM_TOKEN_PURPOSE

    expired_token = jwt.encode(
        {
            "user_id": 1,
            "purpose": STREAM_TOKEN_PURPOSE,
            "exp": int((datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp()),
        },
        STREAM_SECRET_KEY,
        algorithm=STREAM_ALGORITHM,
    )
    response = client.get(
        "/api/parking/stream-auth", cookies={STREAM_COOKIE_NAME: expired_token}
    )
    assert response.status_code == 401


def test_revoked_account_cannot_reuse_stream_cookie(client, db_session):
    admin = _create_admin(db_session)
    stream_cookie = _stream_cookie(client, admin)
    admin.approval_status = ApprovalStatus.rejected
    db_session.commit()

    response = client.get(
        "/api/parking/stream-auth", cookies={STREAM_COOKIE_NAME: stream_cookie}
    )
    assert response.status_code == 403
