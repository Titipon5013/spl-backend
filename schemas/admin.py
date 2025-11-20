from pydantic import BaseModel, EmailStr
from enums import RoleEnum
from typing import Optional, List

class AdminOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    hashed_password: str
    role: RoleEnum

    model_config = {
        "from_attributes": True
    }

class AdminResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: RoleEnum

    model_config = {
        "from_attributes": True
    }

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
