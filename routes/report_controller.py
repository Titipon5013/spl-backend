from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import dependencies
from db.models import Admin
from db.session import get_db
from enums import ApprovalStatus
from services.export_service import ExportService
from services.report_scheduler import trigger_weekly_reports_now

router = APIRouter(tags=["Reports"])


def _require_approved_admin(current_user: Admin = Depends(dependencies.get_current_admin_user)):
    if current_user.approval_status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Approved administrator access required",
        )
    return current_user


@router.post("/api/reports/trigger")
def trigger_weekly_report(
    _: Admin = Depends(_require_approved_admin),
):
    trigger_weekly_reports_now()
    return {"status": "success", "message": "Weekly reports dispatched"}


@router.get("/api/analytics/export")
def export_analytics(
    lot_id: str = Query("CAMT_01"),
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    export_format: str = Query("csv", pattern="^(csv|pdf)$"),
    db: Session = Depends(get_db),
    _: Admin = Depends(_require_approved_admin),
):
    service = ExportService(db)
    try:
        content, filename, media_type = service.export_analytics(
            lot_id, start_date, end_date, export_format
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
