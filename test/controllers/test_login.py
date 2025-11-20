import pytest
from unittest.mock import MagicMock
from main import app
from services.dependencies import get_admin_service
from schemas.admin import AdminOut
from enums import RoleEnum

@pytest.fixture
def mock_admin_service():
    return MagicMock()

def test_login_for_access_token(client, mock_admin_service):
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    
    mock_user = AdminOut(
        id=1,
        username="testuser",
        email="testuser@example.com",
        role=RoleEnum.admin,
        hashed_password="hashed_password"
    )
    mock_admin_service.authenticate_admin.return_value = mock_user
    
    response = client.post(
        "/login",
        data={"username": "testuser@example.com", "password": "testpassword"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"
    
    app.dependency_overrides = {}

def test_login_invalid_password(client, mock_admin_service):
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    mock_admin_service.authenticate_admin.return_value = None
    
    response = client.post(
        "/login",
        data={"username": "testuser@example.com", "password": "wrongpassword"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    
    assert response.status_code == 401
    
    app.dependency_overrides = {}

def test_login_non_existent_user(client, mock_admin_service):
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    mock_admin_service.authenticate_admin.return_value = None
    
    response = client.post(
        "/login",
        data={"username": "nonexistent@example.com", "password": "password"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    
    assert response.status_code == 401
    
    app.dependency_overrides = {}

def test_login_missing_password(client):
    response = client.post(
        "/login",
        data={"username": "testuser@example.com"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 422

def test_login_missing_username(client):
    response = client.post(
        "/login",
        data={"password": "testpassword"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 422
