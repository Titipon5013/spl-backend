from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from services.analytics_service import AnalyticsService
from schemas.analytics import HeatmapResponse, TrendResponse
from datetime import datetime, timedelta
from typing import Optional
from db.models import ParkingSnapshot, ParkingSnapshot2

router = APIRouter()

from schemas.analytics import (
    HeatmapResponse,
    TrendResponse,
    SystemHealthResponse,
    DeviceHeartbeatPayload,
    CameraEventPayload
)

@router.get("/heatmap", response_model=HeatmapResponse)
def get_spatial_heatmap(
    lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
    start_date: Optional[datetime] = Query(None, description="Started Time"),
    end_date: Optional[datetime] = Query(None, description="Ended Time"),
    db: Session = Depends(get_db)
):
    service = AnalyticsService(db)
    return service.get_heatmap_data(lot_id, start_date, end_date)

@router.get("/kpis")
def get_kpis(
    lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
    start_date: Optional[datetime] = Query(None, description="Started Time"),
    end_date: Optional[datetime] = Query(None, description="Ended Time"),
    db: Session = Depends(get_db),
):
    service = AnalyticsService(db)
    end = end_date or datetime.utcnow()
    start = start_date or (end - timedelta(days=7))
    return service.get_kpis(lot_id, start, end)


@router.get("/slots/{spot_id}/events")
def get_slot_event_history(
    spot_id: str,
    lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
    start_date: Optional[datetime] = Query(None, description="Started Time"),
    end_date: Optional[datetime] = Query(None, description="Ended Time"),
    db: Session = Depends(get_db),
):
    service = AnalyticsService(db)
    return service.get_slot_event_history(lot_id, spot_id, start_date, end_date)


@router.get("/trends", response_model=TrendResponse)
def get_occupancy_trends(
    lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
    start_date: datetime = Query(..., description="Started Time"),
    end_date: datetime = Query(..., description="Ended Time"),
    db: Session = Depends(get_db)
):
    service = AnalyticsService(db)
    return service.get_occupancy_trends(lot_id, start_date, end_date)

@router.get("/current")
def get_current_status(
    lot_id: str = Query("CAMT_02", description="Parking Lot ID"),
    db: Session = Depends(get_db)
):
    """
    Pulling real-time data from the latest snapshot (Production Ready)
    """
    if lot_id == "CAMT_01":
        model = ParkingSnapshot
    elif lot_id == "CAMT_02":
        model = ParkingSnapshot2
    else:
        raise HTTPException(status_code=400, detail="Invalid Parking Lot ID")

    latest = db.query(model).filter(
        model.lot_id == lot_id
    ).order_by(model.timestamp.desc()).first()

    if not latest:
        raise HTTPException(
            status_code=404,
            detail="No real-time data available. Waiting for camera sensor ingestion."
        )

    return {
        "available_spaces": latest.available_spaces,
        "total_spaces": latest.total_spaces,
        "occupied_spaces": latest.occupied_spaces,
        "occupacy_rate": latest.occupacy_rate
    }

@router.get("/health", response_model=SystemHealthResponse)
def get_system_health(
        lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
        db: Session = Depends(get_db)
):
    """
    ตรวจสอบสถานะ Orange Pi และ connected camera streams ทั้ง 4 ตัว
    """
    service = AnalyticsService(db)
    return service.get_system_health_status(lot_id)


# ==========================================
# 3. Hardware Ingestion API (รับข้อมูลจาก Orange Pi)
# ==========================================

@router.post("/heartbeat")
def receive_hardware_heartbeat(
        payload: DeviceHeartbeatPayload,
        db: Session = Depends(get_db)
):
    """
    รับสัญญาณ Heartbeat จาก Orange Pi เพื่ออัปเดตสถานะของ Board และ Camera
    (ควรให้ Orange Pi ยิงมาหาเส้นนี้ทุกๆ 1 นาที แม้จะไม่มีรถเข้าออกก็ตาม)
    """
    service = AnalyticsService(db)
    success = service.update_hardware_heartbeat(payload)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update heartbeat")

    return {"status": "success", "message": "Heartbeat received and logged"}


@router.post("/camera/events")
def receive_camera_events(
        payload: CameraEventPayload,
        db: Session = Depends(get_db)
):
    """
    รับข้อมูลเมื่อมีรถเข้าหรือออกช่องจอด
    นำไปบันทึกลง ParkingEventLog และอัปเดต ParkingSnapshot
    """
    service = AnalyticsService(db)
    result = service.process_camera_events(payload)

    return {"status": "success", "message": result}
