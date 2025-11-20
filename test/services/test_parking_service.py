import pytest
from unittest.mock import MagicMock
from services.parking_service import ParkingService
from db.models import ParkingSnapshot
from schemas.parking import ParkingSnapshotResponse

@pytest.fixture
def mock_parking_repo():
    return MagicMock()

@pytest.fixture
def parking_service(mock_parking_repo):
    return ParkingService(mock_parking_repo)

from datetime import datetime

def test_get_latest_snapshot_success(parking_service, mock_parking_repo):
    # Setup
    snapshot_data = {
        "id": 1,
        "lot_id": "CAMT_01",
        "timestamp": datetime.utcnow(),
        "available_spaces": 50,
        "total_spaces": 100,
        "occupied_spaces": 50,
        "occupacy_rate": 50.0,
        "confidence": 0.9,
        "processing_time_seconds": 0.5,
    }
    snapshot = ParkingSnapshot(**snapshot_data)
    mock_parking_repo.get_latest_snapshot.return_value = snapshot
    
    # Execute
    result = parking_service.get_latest_snapshot()
    
    # Assert
    assert isinstance(result, ParkingSnapshotResponse)
    assert result.id == snapshot.id
    mock_parking_repo.get_latest_snapshot.assert_called_once()

def test_get_latest_snapshot_not_found(parking_service, mock_parking_repo):
    # Setup
    mock_parking_repo.get_latest_snapshot.return_value = None
    
    # Execute and Assert
    with pytest.raises(Exception) as excinfo:
        parking_service.get_latest_snapshot()
    assert "No parking snapshot found" in str(excinfo.value)
    mock_parking_repo.get_latest_snapshot.assert_called_once()
