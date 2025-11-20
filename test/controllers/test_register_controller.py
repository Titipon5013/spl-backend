import pytest
from unittest.mock import Mock, MagicMock
from fastapi.testclient import TestClient
from main import app
from services.dependencies import get_plate_request_service
from schemas.request import RequestStatus
from datetime import datetime
import io

client = TestClient(app)

@pytest.fixture
def mock_plate_request_service():
    mock_service = Mock()
    app.dependency_overrides[get_plate_request_service] = lambda: mock_service
    yield mock_service
    app.dependency_overrides = {}


def test_register_plate_success(mock_plate_request_service):
    # The service returns a model instance, the controller returns a dict
    service_return_obj = MagicMock()
    service_return_obj.id = 1
    service_return_obj.status = RequestStatus.pending
    service_return_obj.submitted_at = datetime.now()

    mock_plate_request_service.create_plate_request.return_value = service_return_obj

    form_data = {
        "name": "testuser",
        "email": "test@example.com",
        "plate_number": "ABC-123",
    }
    file_content = b"fake image data"
    files = {"photo": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}

    response = client.post("/register", data=form_data, files=files)

    assert response.status_code == 200
    json_response = response.json()
    assert json_response["request_id"] == service_return_obj.id
    assert json_response["status"] == service_return_obj.status.value
    mock_plate_request_service.create_plate_request.assert_called_once()


def test_register_plate_missing_plate_number():
    app.dependency_overrides = {} # Reset overrides to test real dependency
    form_data = {
        "name": "testuser",
        "email": "test@example.com",
    } # Missing plate_number
    files = {"photo": ("test.jpg", b"fake image data", "image/jpeg")}

    response = client.post("/register", data=form_data, files=files)
    assert response.status_code == 422
    assert "plate_number" in response.text

def test_register_plate_invalid_email():
    app.dependency_overrides = {} # Reset overrides
    form_data = {
        "plate_number": "ABC-123",
        "name": "testuser",
        "email": "not-an-email",
    }
    files = {"photo": ("test.jpg", b"fake image data", "image/jpeg")}

    response = client.post("/register", data=form_data, files=files)
    assert response.status_code == 422
    assert "email" in response.text

def test_register_plate_no_image():
    app.dependency_overrides = {} # Reset overrides
    form_data = {
        "plate_number": "ABC-123",
        "name": "testuser",
        "email": "test@example.com",
    }
    # Missing files payload

    response = client.post("/register", data=form_data)
    assert response.status_code == 422
    assert "photo" in response.text
