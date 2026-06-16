from pydantic import BaseModel, EmailStr
from enums import RoleEnum, ApprovalStatus, AuthProvider
from typing import Optional, List
from datetime import datetime


class AdminOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    hashed_password: Optional[str] = None
    role: RoleEnum
    approval_status: ApprovalStatus = ApprovalStatus.approved
    auth_provider: AuthProvider = AuthProvider.local

    model_config = {
        "from_attributes": True
    }


class AdminResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: RoleEnum
    approval_status: ApprovalStatus = ApprovalStatus.approved
    auth_provider: AuthProvider = AuthProvider.local
    created_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }


class AdminAccessRequestResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    status: ApprovalStatus
    auth_provider: AuthProvider
    created_at: datetime
    avatar: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class AdminAccessStatusUpdate(BaseModel):
    status: ApprovalStatus

class AdminListResponse(BaseModel):
    admins: List[AdminResponse]
    total_pages: int

class AdminCreate(BaseModel):
    username: str
    email: str
    password: str
    role: RoleEnum

class AdminUpdate(BaseModel):
    username: Optional[str] | None = None
    email: Optional[EmailStr] | None = None
    password: Optional[str] | None = None
    role: Optional[RoleEnum]

    model_config = {
        "use_enum_values": True
    }
