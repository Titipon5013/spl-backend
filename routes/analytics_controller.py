from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from services.analytics_service import AnalyticsService
from schemas.analytics import HeatmapResponse, TrendResponse
from datetime import datetime
from typing import Optional
from db.models import ParkingSnapshot2  # <-- นำเข้า Model สำหรับกล้อง 2

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

@router.get("/trends", response_model=TrendResponse)
def get_occupancy_trends(
    lot_id: str = Query("CAMT_01", description="Parking Lot ID"),
    start_date: datetime = Query(..., description="Started Time"),
    end_date: datetime = Query(..., description="Ended Time"),
    db: Session = Depends(get_db)
):
    """
    Pulling statics data (Peak Hour)
    """
    service = AnalyticsService(db)
    return service.get_occupancy_trends(lot_id, start_date, end_date)


@router.get("/current")
def get_current_status(
        lot_id: str = Query("CAMT_02", description="Parking Lot ID"),
        db: Session = Depends(get_db)
):
    """
    Pulling real-time data from the latest snapshot
    """
    latest = db.query(ParkingSnapshot2).filter(
        ParkingSnapshot2.lot_id == lot_id
    ).order_by(ParkingSnapshot2.timestamp.desc()).first()

    # ----------------------------------------------------
    # 🚨 โซน Mockup: ถ้ายังไม่มีข้อมูลใน DB ให้ส่งข้อมูลทิพย์ไปโชว์ก่อน
    # ----------------------------------------------------
    if not latest:
        if lot_id == "CAMT_02":
            return {
                "available_spaces": 26,
                "total_spaces": 41,
                "occupied_spaces": 15,
                "occupacy_rate": 36.5
            }
        elif lot_id == "CAMT_01":
            return {
                "available_spaces": 6,
                "total_spaces": 34,
                "occupied_spaces": 28,
                "occupacy_rate": 82.3
            }

        # ถ้าเป็นลานอื่นที่ไม่ได้ Mock ไว้ ค่อยพ่น 404
        raise HTTPException(status_code=404, detail="No parking data found in the database")

    # ----------------------------------------------------
    # ✅ โซนของจริง: ถ้ามีข้อมูลใน DB แล้ว ก็ดึงของจริงมาใช้เลย
    # ----------------------------------------------------
    return {
        "available_spaces": latest.available_spaces,
        "total_spaces": latest.total_spaces,
        "occupied_spaces": latest.occupied_spaces,
        "occupacy_rate": latest.occupacy_rate
    }