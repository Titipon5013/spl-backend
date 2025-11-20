import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from main import app
from schemas.admin import AdminResponse, AdminCreate, AdminUpdate
from enums import RoleEnum
from services.dependencies import get_admin_service
from auth.dependencies import get_current_admin_user

client = TestClient(app)

@pytest.fixture
def mock_admin_service():
    return MagicMock()

@pytest.fixture
def mock_current_user():
    return MagicMock()

def test_get_all_user(mock_admin_service, mock_current_user):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: mock_current_user
    
    mock_admin_service.get_all_admins.return_value = [
        AdminResponse(id=1, username="test1", email="test1@example.com", role=RoleEnum.admin),
        AdminResponse(id=2, username="test2", email="test2@example.com", role=RoleEnum.operator)
    ]
    
    # Execute
    response = client.get("/admins/")
    
    # Assert
    assert response.status_code == 200
    assert len(response.json()) == 2
    mock_admin_service.get_all_admins.assert_called_once()
    
    # Teardown
    app.dependency_overrides = {}

def test_get_all_user_unauthorized(mock_admin_service):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: None
    
    # Execute
    response = client.get("/admins/")
    
    # Assert
    assert response.status_code == 401
    
    # Teardown
    app.dependency_overrides = {}

def test_create_user(mock_admin_service, mock_current_user):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: mock_current_user
    
    new_admin = AdminCreate(username="newadmin", email="new@example.com", password="password", role=RoleEnum.admin)
    mock_admin_service.create_admin.return_value = AdminResponse(id=3, username="newadmin", email="new@example.com", role=RoleEnum.admin)
    
    # Execute
    response = client.post("/admins/", json=new_admin.model_dump())
    
    # Assert
    assert response.status_code == 201
    mock_admin_service.create_admin.assert_called_once()
    
    # Teardown
    app.dependency_overrides = {}

def test_create_user_unauthorized(mock_admin_service):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: None
    
    new_admin = AdminCreate(username="newadmin", email="new@example.com", password="password", role=RoleEnum.admin)
    
    # Execute
    response = client.post("/admins/", json=new_admin.model_dump())
    
    # Assert
    assert response.status_code == 401
    
    # Teardown
    app.dependency_overrides = {}

def test_edit_user(mock_admin_service, mock_current_user):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: mock_current_user
    
    admin_update = AdminUpdate(username="updated", role=RoleEnum.admin)
    mock_admin_service.update_admin.return_value = AdminResponse(id=1, username="updated", email="test1@example.com", role=RoleEnum.admin)
    
    # Execute
    response = client.patch("/admins/1", json=admin_update.model_dump(exclude_unset=True))
    
    # Assert
    assert response.status_code == 200
    mock_admin_service.update_admin.assert_called_once()
    
    # Teardown
    app.dependency_overrides = {}

def test_edit_user_unauthorized(mock_admin_service):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: None
    
    admin_update = AdminUpdate(username="updated", role=RoleEnum.admin)
    
    # Execute
    response = client.patch("/admins/1", json=admin_update.model_dump(exclude_unset=True))
    
    # Assert
    assert response.status_code == 401
    
    # Teardown
    app.dependency_overrides = {}

def test_delete_user(mock_admin_service, mock_current_user):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: mock_current_user
    
    # Execute
    response = client.delete("/admins/1")
    
    # Assert
    assert response.status_code == 204
    mock_admin_service.delete_admin.assert_called_once()
    
    # Teardown
    app.dependency_overrides = {}

def test_delete_user_unauthorized(mock_admin_service):
    # Setup
    app.dependency_overrides[get_admin_service] = lambda: mock_admin_service
    app.dependency_overrides[get_current_admin_user] = lambda: None
    
    # Execute
    response = client.delete("/admins/1")
    
    # Assert
    assert response.status_code == 401
    
    # Teardown
    app.dependency_overrides = {}
