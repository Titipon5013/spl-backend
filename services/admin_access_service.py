from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from db.models import Admin
from enums import ApprovalStatus, AuthProvider, RoleEnum
from schemas.admin import AdminAccessRequestResponse, AdminAccessStatusUpdate
from services.email_service import EmailService


class AdminAccessService:
    def __init__(self, db: Session):
        self.db = db
        self.email_service = EmailService()

    def list_access_requests(
        self, status_filter: Optional[ApprovalStatus] = None
    ) -> List[AdminAccessRequestResponse]:
        query = self.db.query(Admin).filter(Admin.auth_provider == AuthProvider.google)
        if status_filter:
            query = query.filter(Admin.approval_status == status_filter)
        admins = query.order_by(Admin.created_at.desc()).all()
        return [self._to_response(admin) for admin in admins]

    def update_access_status(
        self, admin_id: int, payload: AdminAccessStatusUpdate
    ) -> AdminAccessRequestResponse:
        admin = self.db.query(Admin).filter(Admin.id == admin_id).first()
        if not admin:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

        if payload.status == ApprovalStatus.revoked:
            admin.approval_status = ApprovalStatus.revoked
            admin.revoked_at = datetime.utcnow()
        elif payload.status == ApprovalStatus.approved:
            admin.approval_status = ApprovalStatus.approved
            admin.revoked_at = None
            self.email_service.send_line_qr_email(admin.email, admin.username)
        elif payload.status == ApprovalStatus.rejected:
            admin.approval_status = ApprovalStatus.rejected
            admin.revoked_at = None
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status transition for access management",
            )

        self.db.commit()
        self.db.refresh(admin)
        return self._to_response(admin)

    def _to_response(self, admin: Admin) -> AdminAccessRequestResponse:
        avatar = (
            f"https://ui-avatars.com/api/?name={admin.username}&background=0D8ABC&color=fff"
        )
        return AdminAccessRequestResponse(
            id=admin.id,
            name=admin.username,
            email=admin.email,
            status=admin.approval_status,
            auth_provider=admin.auth_provider,
            created_at=admin.created_at,
            avatar=avatar,
        )
