import pytest
from unittest.mock import Mock, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import app
from auth.dependencies import get_current_admin_user
from db.models import Admin
from services.dependencies import get_plate_request_service
from schemas.request import LicensePlateRequestWithClient, RequestStatus, RequestStatusUpdate

client = TestClient(app)

@pytest.fixture
def mock_plate_request_service():
    mock_service = Mock()
    app.dependency_overrides[get_plate_request_service] = lambda: mock_service
    yield mock_service
    app.dependency_overrides = {}

@pytest.fixture
def mock_get_current_user():
    mock_user = Admin(id=1, email="admin@example.com", role="admin")
    app.dependency_overrides[get_current_admin_user] = lambda: mock_user
    yield mock_user
    app.dependency_overrides = {}

def test_list_requests_success(mock_plate_request_service, mock_get_current_user):
    mock_requests = [
        LicensePlateRequestWithClient(id=1, plate_number="ABC-123", plate_image_url="url1", status=RequestStatus.pending, username="Test User", user_email="test@example.com"),
        LicensePlateRequestWithClient(id=2, plate_number="XYZ-789", plate_image_url="url2", status=RequestStatus.approved, username="Another User", user_email="another@example.com"),
    ]
    mock_plate_request_service.get_all_plate_requests.return_value = mock_requests

    response = client.get("/requests")
    
    assert response.status_code == 200
    assert response.json() == [req.model_dump() for req in mock_requests]
    mock_plate_request_service.get_all_plate_requests.assert_called_once_with(mock_get_current_user, None, 1, 10)

def test_list_requests_unauthorized():
    app.dependency_overrides = {}
    response = client.get("/requests")
    assert response.status_code == 401

def test_update_request_status_success(mock_plate_request_service, mock_get_current_user):
    request_id = 1
    payload = RequestStatusUpdate(status=RequestStatus.approved)
    mock_updated_request = LicensePlateRequestWithClient(id=request_id, plate_number="ABC-123", plate_image_url="url1", status=RequestStatus.approved, username="Test User", user_email="test@example.com")
    mock_plate_request_service.update_plate_status.return_value = mock_updated_request

    response = client.put(f"/requests/{request_id}", json=payload.model_dump())

    assert response.status_code == 200
    assert response.json() == mock_updated_request.model_dump()
    mock_plate_request_service.update_plate_status.assert_called_once_with(request_id, payload, mock_get_current_user)

def test_update_request_status_unauthorized():
    app.dependency_overrides = {}
    response = client.put("/requests/1", json={"status": "approved"})
    assert response.status_code == 401

def test_update_request_status_not_found(mock_plate_request_service, mock_get_current_user):
    request_id = 999
    payload = RequestStatusUpdate(status=RequestStatus.approved)
    mock_plate_request_service.update_plate_status.side_effect = HTTPException(status_code=404, detail="Request not found")

    response = client.put(f"/requests/{request_id}", json=payload.dict())
    assert response.status_code == 404
    assert response.json() == {"detail": "Request not found"}

def test_update_request_status_invalid_status(mock_get_current_user):
    response = client.put("/requests/1", json={"status": "invalid_status"})
    assert response.status_code == 422
