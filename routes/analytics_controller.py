from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from services.analytics_service import AnalyticsService
from schemas.analytics import HeatmapResponse, TrendResponse, SystemHealthResponse
from datetime import datetime, timedelta
from typing import Optional
from db.models import ParkingSnapshot, ParkingSnapshot2, ParkingEventLog
from sqlalchemy import desc

router = APIRouter()

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

# ==========================================
# 👇 Endpoint หลักสำหรับแสดงผล Real-time บน Dashboard
# ==========================================
@router.get("/current")
def get_current_status(
    lot_id: str = Query("CAMT_02", description="Parking Lot ID"),
    db: Session = Depends(get_db)
):
    """
    ดึงข้อมูลภาพรวมล่าสุด + สถานะรายช่อง (Real-time Dashboard)
    """
    if lot_id == "CAMT_01":
        model = ParkingSnapshot
    elif lot_id == "CAMT_02":
        model = ParkingSnapshot2
    else:
        raise HTTPException(status_code=400, detail="Invalid Parking Lot ID")

    # 1. ดึงภาพรวม
    latest = db.query(model).filter(
        model.lot_id == lot_id
    ).order_by(model.timestamp.desc()).first()

    if not latest:
        raise HTTPException(
            status_code=404,
            detail="No real-time data available. Waiting for AI Worker ingestion."
        )

    # 2. ดึงสถานะรายช่องล่าสุด (เพื่อไปวาดกล่องเขียว/แดงบนหน้าเว็บ)
    # limit ตามจำนวนช่องในลานจอด (เช่น 30 หรือ 29)
    latest_events = db.query(ParkingEventLog)\
        .filter(ParkingEventLog.lot_id == lot_id)\
        .order_by(desc(ParkingEventLog.timestamp))\
        .limit(latest.total_spaces)\
        .all()

    return {
        "lot_id": latest.lot_id,
        "available_spaces": latest.available_spaces,
        "total_spaces": latest.total_spaces,
        "occupied_spaces": latest.occupied_spaces,
        "occupancy_rate": latest.occupacy_rate, # 👈 ระวังชื่อนี้ใน frontend ต้องแมตช์ด้วยนะครับ (คุณสะกดใน model เป็น occupacy_rate)
        "last_update": latest.timestamp,
        "spots": [{"spot_id": e.spot_id, "is_occupied": e.is_occupied} for e in latest_events]
    }

@router.get("/health", response_model=SystemHealthResponse)
def get_system_health(
        lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
        db: Session = Depends(get_db)
):
    """
    ตรวจสอบสถานะ Hardware และ Camera Streams
    """
    service = AnalyticsService(db)
    return service.get_system_health_status(lot_id)