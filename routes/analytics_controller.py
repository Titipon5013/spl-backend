from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from services.analytics_service import AnalyticsService
from schemas.analytics import HeatmapResponse, TrendResponse, SystemHealthResponse, CameraSnapshotPayload
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


@router.get("/current")
def get_current_status(
    lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
    db: Session = Depends(get_db)
):
    cam1_latest = db.query(ParkingSnapshot).order_by(ParkingSnapshot.timestamp.desc()).first()
    cam2_latest = db.query(ParkingSnapshot2).order_by(ParkingSnapshot2.timestamp.desc()).first()

    if not cam1_latest and not cam2_latest:
        raise HTTPException(
            status_code=404,
            detail="No real-time data available. Waiting for AI Worker ingestion."
        )

    master_data = cam1_latest if cam1_latest else cam2_latest
    target_lot_id = "CAMT_01" if master_data == cam1_latest else "CAMT_02"

    zone_a = [f"A{i}" for i in range(1, 14)]     # A1 - A13
    zone_c = [f"C{i}" for i in range(1, 16)]     # C1 - C15
    zone_b = [f"B{i:02d}" for i in range(1, 7)]  # B01 - B06
    all_spot_ids = zone_a + zone_c + zone_b

    spots_data = []
    for i, sid in enumerate(all_spot_ids):
        is_occupied = True if i < master_data.occupied_spaces else False
        spots_data.append({
            "spot_id": sid,
            "is_occupied": is_occupied
        })

    return {
        "lot_id": lot_id,
        "available_spaces": master_data.available_spaces,
        "total_spaces": 34, # ล็อกเป้าหมายไว้ที่ 34
        "occupied_spaces": master_data.occupied_spaces,
        "occupancy_rate": master_data.occupacy_rate,
        "last_update": master_data.timestamp,
        "spots": spots_data, # ส่งผังที่อัปเดตแล้วไปให้หน้าเว็บ
        "active_camera": target_lot_id
    }


@router.get("/health", response_model=SystemHealthResponse)
def get_system_health(
        lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
        db: Session = Depends(get_db)
):
    service = AnalyticsService(db)
    return service.get_system_health_status(lot_id)


@router.post("/sync")
def sync_parking_data(
        payload: CameraSnapshotPayload,
        db: Session = Depends(get_db)
):
    service = AnalyticsService(db)
    try:
        result = service.process_orange_pi_snapshot(payload)
        return {"status": "success", "detail": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))