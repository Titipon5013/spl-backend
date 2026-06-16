from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import dependencies
from db.models import Admin
from db.session import get_db
from enums import ApprovalStatus, RoleEnum
from schemas.admin import AdminAccessRequestResponse, AdminAccessStatusUpdate
from services.admin_access_service import AdminAccessService

router = APIRouter(tags=["Admin Access"])


def _require_approved_admin(current_user: Admin = Depends(dependencies.get_current_admin_user)):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


@router.get("/api/admin-access/requests", response_model=List[AdminAccessRequestResponse])
def list_admin_access_requests(
    status: Optional[ApprovalStatus] = None,
    db: Session = Depends(get_db),
    _: Admin = Depends(_require_approved_admin),
):
    service = AdminAccessService(db)
    return service.list_access_requests(status)


@router.put(
    "/api/admin-access/requests/{admin_id}",
    response_model=AdminAccessRequestResponse,
)
def update_admin_access_request(
    admin_id: int,
    payload: AdminAccessStatusUpdate,
    db: Session = Depends(get_db),
    _: Admin = Depends(_require_approved_admin),
):
    service = AdminAccessService(db)
    return service.update_access_status(admin_id, payload)
