import pytest
from unittest.mock import Mock, MagicMock, patch
from fastapi import HTTPException
from services.plate_request_service import PlateRequestService
from schemas.request import LicensePlateRequestWithClient, RequestStatusUpdate, LicensePlateRequestCreate
from db.models import Admin, User, LicensePlateRequest
from enums import RequestStatus

@pytest.fixture
def mock_repo():
    return Mock()

@pytest.fixture
def plate_request_service(mock_repo):
    return PlateRequestService(mock_repo)

def test_get_all_plate_requests_success(plate_request_service, mock_repo):
    mock_user = Admin(id=1, email="admin@example.com", role="admin")
    mock_requests = [
        MagicMock(spec=LicensePlateRequest, id=1, plate_number="ABC-123", plate_image_url="url1", status=RequestStatus.pending, user=User(name="Test", email="test@example.com")),
        MagicMock(spec=LicensePlateRequest, id=2, plate_number="XYZ-789", plate_image_url="url2", status=RequestStatus.approved, user=User(name="Another", email="another@example.com"))
    ]
    mock_repo.list_requests_with_user.return_value = mock_requests

    result = plate_request_service.get_all_plate_requests(mock_user)

    assert len(result) == 2
    assert result[0].plate_number == "ABC-123"
    assert result[1].username == "Another"
    mock_repo.list_requests_with_user.assert_called_once()

def test_get_all_plate_requests_unauthorized(plate_request_service):
    mock_user = Admin(id=1, email="user@example.com", role="user")
    with pytest.raises(HTTPException) as exc_info:
        plate_request_service.get_all_plate_requests(mock_user)
    assert exc_info.value.status_code == 401

@patch('services.plate_request_service.upload_to_s3')
def test_create_plate_request(mock_upload_to_s3, plate_request_service, mock_repo):
    mock_upload_to_s3.return_value = "http://s3.com/image.jpg"
    form_data = {
        "name": "test",
        "email": "test@example.com",
        "plate_number": "NEW-123",
        "plate_photo": "fake_photo_data"
    }
    
    request_data = LicensePlateRequestCreate(
        username=form_data["name"],
        user_email=form_data["email"],
        plate_number=form_data["plate_number"],
        plate_image_url="http://s3.com/image.jpg",
        status=RequestStatus.pending
    )
    
    mock_created_request = LicensePlateRequest(id=3, plate_number="NEW-123", user_id=1, plate_image_url="http://s3.com/image.jpg", status=RequestStatus.pending)
    mock_repo.create_license_plate_request.return_value = mock_created_request

    result = plate_request_service.create_plate_request(form_data)

    mock_upload_to_s3.assert_called_once_with("fake_photo_data")
    mock_repo.create_license_plate_request.assert_called_once_with(request_data)
    assert result == mock_created_request

def test_update_plate_status_approved(plate_request_service, mock_repo):
    mock_user = Admin(id=1, email="admin@example.com", role="admin")
    req_id = 1
    new_status = RequestStatusUpdate(status=RequestStatus.approved)
    
    mock_updated_req = LicensePlateRequest(id=req_id, plate_number="ABC-123", user_id=1, plate_image_url="url", status=RequestStatus.approved)
    mock_repo.update_req_status.return_value = mock_updated_req

    result = plate_request_service.update_plate_status(req_id, new_status, mock_user)

    mock_repo.update_req_status.assert_called_once_with(req_id, new_status)
    mock_repo.add_plate.assert_called_once()
    
    # Check the actual object passed to add_plate
    added_plate = mock_repo.add_plate.call_args[0][0]
    assert added_plate.plate_number == mock_updated_req.plate_number
    assert added_plate.user_id == mock_updated_req.user_id
    assert added_plate.plate_image_url == mock_updated_req.plate_image_url
    
    assert result == mock_updated_req

def test_update_plate_status_rejected(plate_request_service, mock_repo):
    mock_user = Admin(id=1, email="admin@example.com", role="admin")
    req_id = 1
    new_status = RequestStatusUpdate(status=RequestStatus.rejected)

    mock_updated_req = LicensePlateRequest(id=req_id, status=RequestStatus.rejected)
    mock_repo.update_req_status.return_value = mock_updated_req

    plate_request_service.update_plate_status(req_id, new_status, mock_user)

    mock_repo.add_plate.assert_not_called()

def test_update_plate_status_unauthorized(plate_request_service):
    mock_user = Admin(id=1, email="user@example.com", role="user")
    with pytest.raises(HTTPException) as exc_info:
        plate_request_service.update_plate_status(1, RequestStatusUpdate(status=RequestStatus.approved), mock_user)
    assert exc_info.value.status_code == 401
