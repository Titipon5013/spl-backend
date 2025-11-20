import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from services.plate_service import PlateService
from schemas.request import LicensePlateCreate, LicensePlateUpdate
from db.models import Admin
from enums import RoleEnum

@pytest.fixture
def mock_plate_repo():
    return MagicMock()

@pytest.fixture
def admin_user():
    return Admin(id=1, role=RoleEnum.admin)

@pytest.fixture
def operator_user():
    return Admin(id=2, role=RoleEnum.operator)

@pytest.fixture
def unauthorized_user():
    return Admin(id=3, role="user")

def test_get_all_plates_admin(mock_plate_repo, admin_user):
    service = PlateService(mock_plate_repo)
    service.get_all_plates(admin_user)
    mock_plate_repo.get_plate_with_user.assert_called_once()

def test_get_all_plates_operator(mock_plate_repo, operator_user):
    service = PlateService(mock_plate_repo)
    service.get_all_plates(operator_user)
    mock_plate_repo.get_plate_with_user.assert_called_once()

def test_get_all_plates_unauthorized(mock_plate_repo, unauthorized_user):
    service = PlateService(mock_plate_repo)
    with pytest.raises(HTTPException) as excinfo:
        service.get_all_plates(unauthorized_user)
    assert excinfo.value.status_code == 401

def test_create_plate_admin(mock_plate_repo, admin_user):
    service = PlateService(mock_plate_repo)
    payload = LicensePlateCreate(user_email="test@example.com", username="test", plate_number="123", plate_image_url="url")
    service.create_plate(admin_user, payload)
    mock_plate_repo.create_plate.assert_called_once_with(payload)

def test_create_plate_operator(mock_plate_repo, operator_user):
    service = PlateService(mock_plate_repo)
    payload = LicensePlateCreate(user_email="test@example.com", username="test", plate_number="123", plate_image_url="url")
    service.create_plate(operator_user, payload)
    mock_plate_repo.create_plate.assert_called_once_with(payload)

def test_create_plate_unauthorized(mock_plate_repo, unauthorized_user):
    service = PlateService(mock_plate_repo)
    payload = LicensePlateCreate(user_email="test@example.com", username="test", plate_number="123", plate_image_url="url")
    with pytest.raises(HTTPException) as excinfo:
        service.create_plate(unauthorized_user, payload)
    assert excinfo.value.status_code == 401

def test_update_plate_admin(mock_plate_repo, admin_user):
    service = PlateService(mock_plate_repo)
    plate = MagicMock()
    mock_plate_repo.find_plate_by_id.return_value = plate
    payload = LicensePlateUpdate(plate_number="456")
    service.update_plate(1, payload, admin_user)
    mock_plate_repo.update_plate.assert_called_once_with(plate, payload)

def test_update_plate_operator(mock_plate_repo, operator_user):
    service = PlateService(mock_plate_repo)
    plate = MagicMock()
    mock_plate_repo.find_plate_by_id.return_value = plate
    payload = LicensePlateUpdate(plate_number="456")
    service.update_plate(1, payload, operator_user)
    mock_plate_repo.update_plate.assert_called_once_with(plate, payload)

def test_update_plate_unauthorized(mock_plate_repo, unauthorized_user):
    service = PlateService(mock_plate_repo)
    payload = LicensePlateUpdate(plate_number="456")
    with pytest.raises(HTTPException) as excinfo:
        service.update_plate(1, payload, unauthorized_user)
    assert excinfo.value.status_code == 401

def test_update_plate_not_found(mock_plate_repo, admin_user):
    service = PlateService(mock_plate_repo)
    mock_plate_repo.find_plate_by_id.return_value = None
    payload = LicensePlateUpdate(plate_number="456")
    with pytest.raises(HTTPException) as excinfo:
        service.update_plate(1, payload, admin_user)
    assert excinfo.value.status_code == 404

def test_delete_plate_admin(mock_plate_repo, admin_user):
    service = PlateService(mock_plate_repo)
    plate = MagicMock()
    mock_plate_repo.find_plate_by_id.return_value = plate
    service.delete_plate(1, admin_user)
    mock_plate_repo.delete_plate.assert_called_once_with(plate)

def test_delete_plate_operator(mock_plate_repo, operator_user):
    service = PlateService(mock_plate_repo)
    plate = MagicMock()
    mock_plate_repo.find_plate_by_id.return_value = plate
    service.delete_plate(1, operator_user)
    mock_plate_repo.delete_plate.assert_called_once_with(plate)

def test_delete_plate_unauthorized(mock_plate_repo, unauthorized_user):
    service = PlateService(mock_plate_repo)
    with pytest.raises(HTTPException) as excinfo:
        service.delete_plate(1, unauthorized_user)
    assert excinfo.value.status_code == 401

def test_delete_plate_not_found(mock_plate_repo, admin_user):
    service = PlateService(mock_plate_repo)
    mock_plate_repo.find_plate_by_id.return_value = None
    with pytest.raises(HTTPException) as excinfo:
        service.delete_plate(1, admin_user)
    assert excinfo.value.status_code == 404
