from datetime import datetime, timedelta
from jose import JWTError, jwt
from schemas.token import TokenData
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, status, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from db import session, models
from schemas.admin import AdminOut
import os
from dotenv import load_dotenv

load_dotenv()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

ALOGRITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
SECRET_KEY = os.getenv("SECRET_KEY")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY must be set in config and cannot be None")

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, ALOGRITHM)
    return encoded_jwt


def verify_access_token(token: str, credentials_exception):
    try:
        if not SECRET_KEY:
            raise ValueError("SECRET_KEY must be set in config and cannot be None")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALOGRITHM])
        id_ = payload.get("user_id")
        if id_ is None:
            raise credentials_exception
        token_data = TokenData(id=str(id_))
    except JWTError:
        raise credentials_exception

    return token_data


async def get_token(token: str = Depends(oauth2_scheme)):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_current_admin_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(session.get_db)
) -> AdminOut:
    """
    Resolves the current admin user from the provided JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token_data = verify_access_token(token, credentials_exception)
        user = db.query(models.Admin).filter(models.Admin.id == token_data.id).first()
        if not user:
            raise credentials_exception
        return AdminOut.model_validate(user)
    except JWTError:
        raise credentials_exception
