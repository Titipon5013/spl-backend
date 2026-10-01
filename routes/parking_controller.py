import os

import requests
from enum import Enum
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, status, HTTPException, Request
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from schemas.parking import ParkingSnapshotResponse
from services.dependencies import get_parking_service
from services.parking_service import ParkingService

from auth.dependencies import get_current_admin_role, get_current_admin_user, verify_access_token
from schemas.admin import AdminOut
from enums import ApprovalStatus, RoleEnum
from db import models
from db.session import get_db

router = APIRouter(prefix="/api/parking", tags=["parking"])
stream_router = APIRouter(tags=["protected camera streams"])


class CameraStream(str, Enum):
    parking1 = "parking1"
    parking2 = "parking2"
    license1 = "license1"
    license2 = "license2"
    # Existing frontend aliases remain protected while clients migrate.
    parking = "parking"
    license = "license"


EDGE_BASE_URL = os.getenv("EDGE_BASE_URL", "http://10.41.11.31:9696").rstrip("/")
STREAM_COOKIE_NAME = "parking_stream_session"
STREAM_TOKEN_PURPOSE = "parking_stream"
STREAM_COOKIE_MAX_AGE_SECONDS = 5 * 60
STREAM_ALGORITHM = "HS256"
STREAM_SECRET_KEY = os.getenv("SECRET_KEY")
bearer_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")


def _approved_dashboard_user(user: models.Admin) -> AdminOut:
    if user.approval_status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Administrator access is {user.approval_status.value}",
        )
    if user.role not in (RoleEnum.admin, RoleEnum.operator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Management staff only.",
        )
    return AdminOut.model_validate(user)


def verify_management_staff(current_user: AdminOut = Depends(get_current_admin_user)):
    if current_user.approval_status != ApprovalStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Administrator access is {current_user.approval_status.value}",
        )
    if current_user.role not in (RoleEnum.admin, RoleEnum.operator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Management staff only.",
        )
    return current_user


def get_current_stream_user(
    stream_token: str | None = Cookie(default=None, alias=STREAM_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> AdminOut:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid stream session",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not stream_token or not STREAM_SECRET_KEY:
        raise unauthorized

    try:
        claims = jwt.decode(stream_token, STREAM_SECRET_KEY, algorithms=[STREAM_ALGORITHM])
        if claims.get("purpose") != STREAM_TOKEN_PURPOSE:
            raise unauthorized
        user_id = int(claims["user_id"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise unauthorized

    user = db.query(models.Admin).filter(models.Admin.id == user_id).first()
    if not user:
        raise unauthorized
    return _approved_dashboard_user(user)

def verify_camera_staff(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_access_token(token, credentials_exception)
    try:
        user_id = int(token_data.id)
    except (TypeError, ValueError):
        raise credentials_exception

    user = db.query(models.Admin).filter(models.Admin.id == user_id).first()
    if not user:
        raise credentials_exception

    return _approved_dashboard_user(user)

@router.get("/auth/verify-camera")
def check_camera_access(_=Depends(verify_camera_staff)):
    return Response(status_code=status.HTTP_200_OK)


@router.post("/stream-session")
def create_stream_session(
    response: Response,
    bearer_token: str = Depends(bearer_scheme),
    current_user: AdminOut = Depends(get_current_admin_user),
):
    _approved_dashboard_user(current_user)
    if not STREAM_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Authentication is not configured")

    try:
        claims = jwt.decode(bearer_token, STREAM_SECRET_KEY, algorithms=[STREAM_ALGORITHM])
        token_expiry = int(claims["exp"])
        if str(claims.get("user_id")) != str(current_user.id):
            raise ValueError("Token account mismatch")
    except (JWTError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = int(datetime.now(timezone.utc).timestamp())
    cookie_expiry = min(token_expiry, now + STREAM_COOKIE_MAX_AGE_SECONDS)
    max_age = cookie_expiry - now
    if max_age <= 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token expired")

    stream_token = jwt.encode(
        {"user_id": current_user.id, "purpose": STREAM_TOKEN_PURPOSE, "exp": cookie_expiry},
        STREAM_SECRET_KEY,
        algorithm=STREAM_ALGORITHM,
    )
    response.set_cookie(
        key=STREAM_COOKIE_NAME,
        value=stream_token,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"expires_at": cookie_expiry}


@router.get("/stream-auth", status_code=status.HTTP_204_NO_CONTENT)
def validate_stream_session(
    response: Response,
    _: AdminOut = Depends(get_current_stream_user),
):
    response.headers["Cache-Control"] = "no-store"
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/snapshot/latest", response_model=ParkingSnapshotResponse, status_code=status.HTTP_200_OK)
def get_latest_snapshot(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(get_current_admin_role),
):
    return parking_service.get_latest_snapshot()


@router.get("/snapshot2/latest", response_model=ParkingSnapshotResponse, status_code=status.HTTP_200_OK)
def get_latest_snapshot2(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(get_current_admin_role),
):
    return parking_service.get_latest_snapshot2()


@router.get("/inference")
def get_parking1_inference(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff),
):
    image_bytes = parking_service.infer_parking1_snapshot()
    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/inference2")
def get_parking2_inference(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff),
):
    image_bytes = parking_service.infer_parking2_snapshot()
    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/open")
def get_open_gate(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff),
):
    return parking_service.open_gate()


@router.get("/exit-gate/status")
def get_exit_gate_status(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff),
):
    return parking_service.get_exit_gate_status()


@router.post("/exit-gate/start")
def start_exit_gate_service(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff),
):
    return parking_service.start_exit_gate_service()


@router.post("/exit-gate/stop")
def stop_exit_gate_service(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff),
):
    return parking_service.stop_exit_gate_service()


@stream_router.get("/{camera}/")
@stream_router.get("/{camera}")
@stream_router.get("/{camera}/{stream_path:path}")
def proxy_camera_stream(
    camera: CameraStream,
    stream_path: str = "",
    _: AdminOut = Depends(get_current_stream_user),
):
    """Proxy camera HLS content so the edge node is never publicly reachable."""
    upstream_url = f"{EDGE_BASE_URL}/{camera.value}/{stream_path}"
    try:
        upstream = requests.get(upstream_url, timeout=5)
        upstream.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Camera stream is unavailable",
        ) from exc

    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={"Cache-Control": "no-store"},
    )
