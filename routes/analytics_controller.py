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
    # ดึงข้อมูล Snapshot ให้ตรงกับ lot_id ที่ Frontend ร้องขอมา
    if lot_id == "CAMT_01":
        master_data = db.query(ParkingSnapshot).order_by(ParkingSnapshot.timestamp.desc()).first()
    else:
        master_data = db.query(ParkingSnapshot2).order_by(ParkingSnapshot2.timestamp.desc()).first()

    if not master_data:
        raise HTTPException(
            status_code=404,
            detail=f"No real-time data available for {lot_id}. Waiting for AI Worker ingestion."
        )

    # แยกโครงสร้างช่องจอดให้ถูกต้อง: CAMT_01 มี 34 ช่อง (Zone A,B,C), ส่วนลานอื่นใช้ Spot_xx
    if lot_id == "CAMT_01":
        zone_a = [f"A{i}" for i in range(1, 14)]     # A1 - A13
        zone_c = [f"C{i}" for i in range(1, 16)]     # C1 - C15
        zone_b = [f"B{i:02d}" for i in range(1, 7)]  # B01 - B06
        all_spot_ids = zone_a + zone_c + zone_b
    else:
        all_spot_ids = [f"Spot_{str(i).zfill(2)}" for i in range(1, master_data.total_spaces + 1)]

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
        "total_spaces": master_data.total_spaces, # ดึงค่าจริงจาก DB ไม่ Hardcode 34
        "occupied_spaces": master_data.occupied_spaces,
        "occupancy_rate": master_data.occupacy_rate,
        "last_update": master_data.timestamp,
        "spots": spots_data,
        "active_camera": lot_id
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