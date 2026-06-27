from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.session import get_db
from services.analytics_service import AnalyticsService
from schemas.analytics import CameraEventPayload, DeviceHeartbeatPayload

router = APIRouter()


# ==========================================
# 1. Endpoint รับข้อมูลกล้อง (Camera Events)
# ==========================================
@router.post("/camera/events")
def receive_camera_events(payload: CameraEventPayload, db: Session = Depends(get_db)):
    try:
        service = AnalyticsService(db)
        message = service.process_camera_events(payload)
        return {"status": "success", "message": message}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================
# 2. Endpoint รับสัญญาณชีพ (Hardware Heartbeat)
# ==========================================
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

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "success", "message": "Heartbeat received and logged"}
