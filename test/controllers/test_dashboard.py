import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from main import app
from services.dependencies import get_parking_service
from schemas.parking import ParkingSnapshotResponse
from datetime import datetime

@pytest.fixture
def mock_parking_service():
    return MagicMock()

def test_get_latest_snapshot_no_data(client, mock_parking_service):
    app.dependency_overrides[get_parking_service] = lambda: mock_parking_service
    mock_parking_service.get_latest_snapshot.side_effect = HTTPException(status_code=404, detail="No parking snapshot found")
    
    response = client.get("/parking/snapshot/latest")
    
    assert response.status_code == 404
    assert response.json() == {"detail": "No parking snapshot found"}
    
    app.dependency_overrides = {}

def test_get_latest_snapshot_with_data(client, mock_parking_service):
    app.dependency_overrides[get_parking_service] = lambda: mock_parking_service
    
    mock_snapshot = ParkingSnapshotResponse(
        id=1,
        lot_id="CAMT_01",
        timestamp=datetime(2025, 7, 12, 14, 40, 3, 836000),
        available_spaces=50,
        total_spaces=100,
    )
    mock_parking_service.get_latest_snapshot.return_value = mock_snapshot
    
    response = client.get("/parking/snapshot/latest")
    
    assert response.status_code == 200
    data = response.json()
    assert data["available_spaces"] == 50
    
    app.dependency_overrides = {}
