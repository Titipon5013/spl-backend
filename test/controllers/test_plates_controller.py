import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, UploadFile
from main import app
from services.dependencies import get_plate_service
from schemas.request import LicensePlateRequestWithClient as LicensePlateResponse
from auth import dependencies
from enums import RequestStatus

@pytest.fixture
def mock_plate_service():
    return MagicMock()

def test_get_plates(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_plate_service.get_all_plates.return_value = [
        LicensePlateResponse(id=1, user_email="test1@example.com", username="test1", plate_number="123", plate_image_url="url1", status=RequestStatus.approved),
        LicensePlateResponse(id=2, user_email="test2@example.com", username="test2", plate_number="456", plate_image_url="url2", status=RequestStatus.pending),
    ]
    
    response = client.get("/plates")
    
    assert response.status_code == 200
    assert len(response.json()) == 2
    
    app.dependency_overrides = {}

def test_get_plates_unauthorized(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: None
    
    response = client.get("/plates")
    
    assert response.status_code == 401
    
    app.dependency_overrides = {}

@patch("routes.plate_controller.upload_to_s3")
def test_create_plate(mock_upload_to_s3, client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_upload_to_s3.return_value = "fake_url"
    mock_plate_service.create_plate.return_value = LicensePlateResponse(id=1, user_email="test@example.com", username="test", plate_number="123", plate_image_url="fake_url", status=RequestStatus.pending)
    
    response = client.post(
        "/plates",
        data={"email": "test@example.com", "name": "test", "plateNumber": "123"},
        files={"photo": ("test.jpg", b"test", "image/jpeg")},
    )
    
    assert response.status_code == 200
    assert response.json()["plate_image_url"] == "fake_url"
    
    app.dependency_overrides = {}

def test_create_plate_unauthorized(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: None
    
    response = client.post(
        "/plates",
        data={"email": "test@example.com", "name": "test", "plateNumber": "123"},
        files={"photo": ("test.jpg", b"test", "image/jpeg")},
    )
    
    assert response.status_code == 401
    
    app.dependency_overrides = {}

def test_update_plate(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_plate_service.update_plate.return_value = LicensePlateResponse(id=1, user_email="test@example.com", username="test", plate_number="123", plate_image_url="url", status=RequestStatus.approved)
    
    response = client.put("/plates/1", data={"plate_number": "456", "user_email": "test@example.com", "username": "test"})
    
    assert response.status_code == 200
    
    app.dependency_overrides = {}

def test_update_plate_not_found(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_plate_service.update_plate.side_effect = HTTPException(status_code=404, detail="Plate not found")
    
    response = client.put("/plates/1", data={"plate_number": "456", "user_email": "test@example.com", "username": "test"})
    
    assert response.status_code == 404
    
    app.dependency_overrides = {}

def test_update_plate_unauthorized(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_plate_service.update_plate.side_effect = HTTPException(status_code=403, detail="Forbidden")
    
    response = client.put("/plates/1", data={"plate_number": "456", "user_email": "test@example.com", "username": "test"})
    
    assert response.status_code == 403
    
    app.dependency_overrides = {}

def test_delete_plate(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_plate_service.delete_plate.return_value = None
    
    response = client.delete("/plates/1")
    
    assert response.status_code == 200
    
    app.dependency_overrides = {}

def test_delete_plate_not_found(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_plate_service.delete_plate.side_effect = HTTPException(status_code=404, detail="Plate not found")
    
    response = client.delete("/plates/1")
    
    assert response.status_code == 404
    
    app.dependency_overrides = {}

def test_delete_plate_unauthorized(client, mock_plate_service):
    app.dependency_overrides[get_plate_service] = lambda: mock_plate_service
    app.dependency_overrides[dependencies.get_current_admin_user] = lambda: MagicMock()
    mock_plate_service.delete_plate.side_effect = HTTPException(status_code=403, detail="Forbidden")
    
    response = client.delete("/plates/1")
    
    assert response.status_code == 403
    
    app.dependency_overrides = {}
