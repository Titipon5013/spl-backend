import pytest
from unittest.mock import MagicMock
from services.admin_service import AdminService
from db.models import Admin
from enums import RoleEnum
from schemas.admin import AdminOut, AdminCreate, AdminUpdate
from passlib.context import CryptContext
from fastapi import HTTPException

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@pytest.fixture
def mock_admin_repo():
    return MagicMock()

@pytest.fixture
def admin_service(mock_admin_repo):
    return AdminService(mock_admin_repo)

def test_authenticate_admin_success(admin_service, mock_admin_repo):
    # Setup
    email = "test@example.com"
    password = "password123"
    hashed_password = pwd_context.hash(password)
    admin_data = {"id": 1, "email": email, "hashed_password": hashed_password, "role": RoleEnum.admin, "username": "testuser"}
    admin = Admin(**admin_data)
    
    mock_admin_repo.get_admin_by_email.return_value = admin
    
    # Execute
    result = admin_service.authenticate_admin(email, password)
    
    # Assert
    assert result.email == admin.email
    assert result.username == admin.username
    mock_admin_repo.get_admin_by_email.assert_called_once_with(email)

def test_authenticate_admin_invalid_password(admin_service, mock_admin_repo):
    # Setup
    email = "test@example.com"
    password = "password123"
    wrong_password = "wrongpassword"
    hashed_password = pwd_context.hash(password)
    admin_data = {"id": 1, "email": email, "hashed_password": hashed_password, "role": RoleEnum.admin, "username": "testuser"}
    admin = Admin(**admin_data)
    
    mock_admin_repo.get_admin_by_email.return_value = admin
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.authenticate_admin(email, wrong_password)
    assert excinfo.value.status_code == 401
    assert "Invalid credentials" in str(excinfo.value.detail)
    mock_admin_repo.get_admin_by_email.assert_called_once_with(email)

def test_authenticate_admin_non_existent_user(admin_service, mock_admin_repo):
    # Setup
    email = "nonexistent@example.com"
    password = "password123"
    
    mock_admin_repo.get_admin_by_email.return_value = None
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.authenticate_admin(email, password)
    assert excinfo.value.status_code == 401
    assert "Invalid credentials" in str(excinfo.value.detail)
    mock_admin_repo.get_admin_by_email.assert_called_once_with(email)

def test_get_all_admins(admin_service, mock_admin_repo):
    # Setup
    mock_admin_repo.get_all_admins.return_value = [
        Admin(id=1, username="test1", email="test1@example.com", role=RoleEnum.admin, hashed_password=""),
        Admin(id=2, username="test2", email="test2@example.com", role=RoleEnum.operator, hashed_password="")
    ]
    
    # Execute
    result = admin_service.get_all_admins()
    
    # Assert
    assert len(result) == 2
    mock_admin_repo.get_all_admins.assert_called_once()

def test_create_admin(admin_service, mock_admin_repo):
    # Setup
    new_admin = AdminCreate(username="newadmin", email="new@example.com", password="password", role=RoleEnum.admin)
    current_user = Admin(id=1, username="admin", email="admin@example.com", role=RoleEnum.admin, hashed_password="")
    mock_admin_repo.get_admin_by_email.return_value = None
    mock_admin_repo.create_admin.return_value = Admin(id=3, username="newadmin", email="new@example.com", role=RoleEnum.admin, hashed_password="")
    
    # Execute
    result = admin_service.create_admin(new_admin, current_user)
    
    # Assert
    assert result.email == new_admin.email
    mock_admin_repo.get_admin_by_email.assert_called_once_with(new_admin.email)
    mock_admin_repo.create_admin.assert_called_once()

def test_create_admin_duplicate_email(admin_service, mock_admin_repo):
    # Setup
    new_admin = AdminCreate(username="newadmin", email="new@example.com", password="password", role=RoleEnum.admin)
    current_user = Admin(id=1, username="admin", email="admin@example.com", role=RoleEnum.admin, hashed_password="")
    mock_admin_repo.get_admin_by_email.return_value = Admin(id=1, username="test1", email="new@example.com", role=RoleEnum.admin, hashed_password="")
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.create_admin(new_admin, current_user)
    assert excinfo.value.status_code == 400
    assert "Email already registered" in str(excinfo.value.detail)
    mock_admin_repo.get_admin_by_email.assert_called_once_with(new_admin.email)

def test_create_admin_unauthorized(admin_service, mock_admin_repo):
    # Setup
    new_admin = AdminCreate(username="newadmin", email="new@example.com", password="password", role=RoleEnum.admin)
    current_user = Admin(id=1, username="operator", email="operator@example.com", role=RoleEnum.operator, hashed_password="")
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.create_admin(new_admin, current_user)
    assert excinfo.value.status_code == 401
    assert "You are not authorized to perform this action" in str(excinfo.value.detail)

def test_update_admin(admin_service, mock_admin_repo):
    # Setup
    admin_update = AdminUpdate(username="updated", role=RoleEnum.admin)
    current_user = Admin(id=1, username="admin", email="admin@example.com", role=RoleEnum.admin, hashed_password="")
    mock_admin_repo.get_admin_by_id.return_value = Admin(id=1, username="test1", email="test1@example.com", role=RoleEnum.admin, hashed_password="")
    mock_admin_repo.update_admin.return_value = Admin(id=1, username="updated", email="test1@example.com", role=RoleEnum.admin, hashed_password="")
    
    # Execute
    result = admin_service.update_admin(1, admin_update, current_user)
    
    # Assert
    assert result.username == "updated"
    mock_admin_repo.get_admin_by_id.assert_called_once_with(1)
    mock_admin_repo.update_admin.assert_called_once()

def test_update_admin_not_found(admin_service, mock_admin_repo):
    # Setup
    admin_update = AdminUpdate(username="updated", role=RoleEnum.admin)
    current_user = Admin(id=1, username="admin", email="admin@example.com", role=RoleEnum.admin, hashed_password="")
    mock_admin_repo.get_admin_by_id.return_value = None
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.update_admin(1, admin_update, current_user)
    assert excinfo.value.status_code == 404
    assert "User Not found" in str(excinfo.value.detail)
    mock_admin_repo.get_admin_by_id.assert_called_once_with(1)

def test_update_admin_unauthorized(admin_service, mock_admin_repo):
    # Setup
    admin_update = AdminUpdate(username="updated", role=RoleEnum.admin)
    current_user = Admin(id=2, username="operator", email="operator@example.com", role=RoleEnum.operator, hashed_password="")
    mock_admin_repo.get_admin_by_id.return_value = Admin(id=1, username="test1", email="test1@example.com", role=RoleEnum.admin, hashed_password="")
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.update_admin(1, admin_update, current_user)
    assert excinfo.value.status_code == 403
    assert "Operators can only edit themselves" in str(excinfo.value.detail)
    mock_admin_repo.get_admin_by_id.assert_called_once_with(1)

def test_delete_admin(admin_service, mock_admin_repo):
    # Setup
    current_user = Admin(id=1, username="admin", email="admin@example.com", role=RoleEnum.admin, hashed_password="")
    mock_admin_repo.get_admin_by_id.return_value = Admin(id=2, username="test2", email="test2@example.com", role=RoleEnum.operator, hashed_password="")
    
    # Execute
    admin_service.delete_admin(2, current_user)
    
    # Assert
    mock_admin_repo.get_admin_by_id.assert_called_once_with(2)
    mock_admin_repo.delete_admin.assert_called_once_with(2)

def test_delete_admin_not_found(admin_service, mock_admin_repo):
    # Setup
    current_user = Admin(id=1, username="admin", email="admin@example.com", role=RoleEnum.admin, hashed_password="")
    mock_admin_repo.get_admin_by_id.return_value = None
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.delete_admin(1, current_user)
    assert excinfo.value.status_code == 404
    assert "User Not found" in str(excinfo.value.detail)
    mock_admin_repo.get_admin_by_id.assert_called_once_with(1)

def test_delete_admin_unauthorized(admin_service, mock_admin_repo):
    # Setup
    current_user = Admin(id=2, username="operator", email="operator@example.com", role=RoleEnum.operator, hashed_password="")
    mock_admin_repo.get_admin_by_id.return_value = Admin(id=1, username="test1", email="test1@example.com", role=RoleEnum.admin, hashed_password="")
    
    # Execute and Assert
    with pytest.raises(HTTPException) as excinfo:
        admin_service.delete_admin(1, current_user)
    assert excinfo.value.status_code == 403
    assert "Operators can only delete themselves" in str(excinfo.value.detail)
    mock_admin_repo.get_admin_by_id.assert_called_once_with(1)
