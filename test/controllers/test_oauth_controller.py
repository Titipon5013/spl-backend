from unittest.mock import AsyncMock, patch

from db.models import Admin
from enums import ApprovalStatus, AuthProvider


def test_google_login_redirects_to_google(client):
    response = client.get("/api/oauth/google/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth"
    )


@patch("routes.oauth_controller.exchange_code_for_user_info", new_callable=AsyncMock)
def test_google_callback_creates_pending_admin(mock_exchange, client, db_session):
    mock_exchange.return_value = {
        "sub": "google-sub-999",
        "email": "new.oauth@example.com",
        "name": "New OAuth",
    }

    response = client.get("/api/oauth/google/callback?code=fake-code", follow_redirects=False)

    assert response.status_code == 307
    assert "oauth_status=pending" in response.headers["location"]

    admin = db_session.query(Admin).filter(Admin.email == "new.oauth@example.com").one()
    assert admin.auth_provider == AuthProvider.google
    assert admin.approval_status == ApprovalStatus.pending
    assert admin.oauth_sub == "google-sub-999"
