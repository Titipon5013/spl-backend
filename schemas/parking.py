from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class SpotDetail(BaseModel):
    spot_id: str
    is_occupied: bool


class ParkingPayload(BaseModel):
    lot_id: str = "CAMT_01"
    timestamp: Optional[datetime] = None  # fallback to server time if None
    available_spaces: int
    total_spaces: int = 30
    occupied_spaces: int
    occupancy_rate: float
    confidence: float
    processing_time_seconds: float

    spot_details: Optional[List[SpotDetail]] = []


class ParkingSnapshotCreate(ParkingPayload):
    pass


class ParkingSnapshotResponse(BaseModel):
    id: int
    lot_id: str
    timestamp: datetime
    available_spaces: int
    total_spaces: int

    class Config:
        from_attributes = True


class LicensePlatePayload(BaseModel):
    plate_number: str
    plate_image_url: str
    timestamp: Optional[datetime] = None