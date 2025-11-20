from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session
from db.session import get_db
from repository.admin_repository import ImplAdminRepositoryInterface
from schemas.token import TokenData
from schemas.admin import AdminOut
from db.models import Admin
from enums import RoleEnum
from typing import Union
import os

SECRET_KEY = os.getenv("SECRET_KEY", "smarparkinglot")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

def authorize_admin_or_self(
    target_id: int, current_user: Union[Admin, AdminOut], require_admin: bool = False
):
    """
    Authorizes a request if the user is an admin or accessing their own resource.
    """
    # This check is to satisfy mypy, but it should not be necessary
    if isinstance(current_user, Admin):
        if current_user.role == RoleEnum.admin.value:
            return
        if not require_admin and current_user.id == target_id:
            return
    elif isinstance(current_user, AdminOut):
        if current_user.role == RoleEnum.admin:
            return
        if not require_admin and current_user.id == target_id:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not authorized to perform this action",
    )
