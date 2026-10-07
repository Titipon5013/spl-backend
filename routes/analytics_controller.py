from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import and_
from sqlalchemy.orm import Session

from db.session import get_db
from services.analytics_service import AnalyticsService
from schemas.analytics import HeatmapResponse, TrendResponse, SystemHealthResponse, CameraSnapshotPayload
from db.models import GateEvent, ParkingSnapshot, ParkingSnapshot2

router = APIRouter()


@router.get("/gate/counts")
def get_gate_counts(
        day: Optional[date] = Query(None, description="Local date in Asia/Bangkok; defaults to today"),
        gate_id: Optional[str] = Query(None, description="Filter to one gate"),
        db: Session = Depends(get_db),
):
    """Return durable open/close counts and hourly buckets from gate_events."""
    local_tz = ZoneInfo("Asia/Bangkok")
    report_day = day or datetime.now(local_tz).date()
    start = datetime.combine(report_day, time.min, tzinfo=local_tz)
    end = datetime.combine(report_day + timedelta(days=1), time.min, tzinfo=local_tz)

    query = db.query(GateEvent).filter(
        and_(GateEvent.timestamp >= start, GateEvent.timestamp < end)
    )
    if gate_id:
        query = query.filter(GateEvent.gate_id == gate_id)
    events = query.order_by(GateEvent.timestamp.asc()).all()

    hourly = [{"hour": hour, "open_count": 0, "close_count": 0} for hour in range(24)]
    totals = {"open": 0, "close": 0}
    for event in events:
        timestamp = event.timestamp
        if timestamp.tzinfo is None:
            # SQLite drops timezone metadata; stored wall time remains Bangkok.
            timestamp = timestamp.replace(tzinfo=local_tz)
        else:
            timestamp = timestamp.astimezone(local_tz)
        totals[event.event] += 1
        hourly[timestamp.hour][f"{event.event}_count"] += 1

    difference = abs(totals["open"] - totals["close"])
    return {
        "date": report_day.isoformat(),
        "timezone": "Asia/Bangkok",
        "gate_id": gate_id,
        "open_count": totals["open"],
        "close_count": totals["close"],
        "count_difference": difference,
        "possible_missing_events": difference > 1,
        "hourly": hourly,
    }


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
    end = end_date or datetime.now()
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
    service = AnalyticsService(db)

    # 1. ดึงข้อมูล Aggregate จาก Snapshot
    if lot_id == "CAMT_01":
        master_data = db.query(ParkingSnapshot).order_by(ParkingSnapshot.timestamp.desc()).first()
    else:
        master_data = db.query(ParkingSnapshot2).order_by(ParkingSnapshot2.timestamp.desc()).first()

    if not master_data:
        raise HTTPException(
            status_code=404,
            detail=f"No real-time data available for {lot_id}. Waiting for AI Worker ingestion."
        )

    # 2. กำหนดรายชื่อช่องทั้งหมดให้ครบถ้วน (ป้องกันช่องตกหล่น)
    if lot_id == "CAMT_01":
        zone_a = [f"A{i}" for i in range(1, 14)]
        zone_c = [f"C{i}" for i in range(1, 16)]
        zone_b = [f"B{i:02d}" for i in range(1, 7)]
        all_spot_ids = zone_a + zone_c + zone_b
    else:
        all_spot_ids = [f"Spot_{str(i).zfill(2)}" for i in range(1, master_data.total_spaces + 1)]

    # 3. ดึงข้อมูลสถานะล่าสุดของแต่ละช่องจาก Event Log
    latest_events = service._latest_event_per_spot(lot_id)
    spots_dict = {event.spot_id: event.is_occupied for event in latest_events}

    # 4. ประกอบร่างข้อมูลให้ครบทุกช่อง! ช่องไหนไม่มีประวัติให้ถือว่า "ว่าง" (False)
    spots_data = []
    for sid in all_spot_ids:
        # ใช้ .get() ถ้าไม่เจอ sid ใน spots_dict จะคืนค่า False แทน
        is_occ = spots_dict.get(sid, False)
        spots_data.append({
            "spot_id": sid,
            "is_occupied": is_occ
        })

    return {
        "lot_id": lot_id,
        "available_spaces": master_data.available_spaces,
        "total_spaces": master_data.total_spaces,
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
