from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional

from services.dependencies import get_db
from db.models import ParkingSnapshot, ParkingSnapshot2, ParkingEventLog

from services.analytics_service import AnalyticsService
from schemas.analytics import DeviceHeartbeatPayload

router = APIRouter(prefix="/api", tags=["camera-events"])


class EventItem(BaseModel):
    spot_id: str
    status: str


class CameraEventPayload(BaseModel):
    lot_id: str
    total_spaces: int
    available_spaces: int
    occupied_spaces: int
    confidence: float
    processing_time_seconds: float
    events: List[EventItem] = []


@router.post("/camera/events", status_code=201)
def receive_camera_events(payload: CameraEventPayload, db: Session = Depends(get_db)):
    try:
        current_time = datetime.utcnow()
        lot_id = payload.lot_id

        occupancy_rate = (payload.occupied_spaces / payload.total_spaces) if payload.total_spaces > 0 else 0.0

        if lot_id == "CAMT_01":
            new_snapshot = ParkingSnapshot(
                lot_id=lot_id,
                timestamp=current_time,
                available_spaces=payload.available_spaces,
                total_spaces=payload.total_spaces,
                occupied_spaces=payload.occupied_spaces,
                occupacy_rate=occupancy_rate,
                confidence=payload.confidence,
                processing_time_seconds=payload.processing_time_seconds
            )
            db.add(new_snapshot)

        elif lot_id == "CAMT_02":
            new_snapshot = ParkingSnapshot2(
                lot_id=lot_id,
                timestamp=current_time,
                available_spaces=payload.available_spaces,
                total_spaces=payload.total_spaces,
                occupied_spaces=payload.occupied_spaces,
                occupacy_rate=occupancy_rate,
                confidence=payload.confidence,
                processing_time_seconds=payload.processing_time_seconds
            )
            db.add(new_snapshot)

        for event in payload.events:
            new_event_log = ParkingEventLog(
                lot_id=lot_id,
                spot_id=event.spot_id,
                is_occupied=(event.status == "occupied"),
                timestamp=current_time
            )
            db.add(new_event_log)

        db.commit()
        return {"message": f"Successfully logged data for {lot_id}"}

    except Exception as e:
        db.rollback()
        print(f"=====================================")
        print(f"🚨 DATABASE ERROR: {str(e)}")
        print(f"=====================================")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/heartbeat")
def receive_hardware_heartbeat(
        payload: DeviceHeartbeatPayload,
        db: Session = Depends(get_db)
):
    """
    รับสัญญาณ Heartbeat จาก AI Worker เพื่ออัปเดตสถานะความพร้อมใช้งาน (Health) ของกล้องและบอร์ด
    """
    try:
        service = AnalyticsService(db)
        success = service.update_hardware_heartbeat(payload)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to update heartbeat")

        return {"status": "success", "message": "Heartbeat received and logged"}

    except Exception as e:
        print(f"🚨 Heartbeat Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))