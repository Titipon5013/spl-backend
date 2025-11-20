from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enums import RequestStatus

class LicensePlateRequestOut(BaseModel):
    id: int
    plate_number: str
    plate_image_url: str
    status: RequestStatus
    submitted_at: datetime

    class Config:
        orm_mode = True

class RequestStatusUpdate(BaseModel):
    status: RequestStatus  # "approved" or "declined"

class LicensePlateUpdate(BaseModel):
    status: Optional[RequestStatus] = None
    user_email: Optional[EmailStr] = None
    username: Optional[str] = None
    plate_number: Optional[str] = None
    plate_image_url: Optional[str] = None

class LicensePlateRequestCreate(BaseModel):
    plate_number: str
    plate_image_url: str
    status: RequestStatus = RequestStatus.pending
    username: str
    user_email: EmailStr

class LicensePlateRequestWithClient(BaseModel):
    id: int
    plate_number: str
    plate_image_url: str
    status: RequestStatus
    username: str
    user_email: EmailStr

    class Config:
        orm_mode = True

class LicensePlateCreate(BaseModel):
    plate_number: str
    plate_image_url: str
    username: str
    user_email: EmailStr
