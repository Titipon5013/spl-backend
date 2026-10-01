from fastapi import APIRouter, Depends, status, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from schemas.parking import ParkingSnapshotResponse
from services.dependencies import get_parking_service
from services.parking_service import ParkingService

from auth.dependencies import get_current_admin_user, verify_access_token
from schemas.admin import AdminOut
from enums import RoleEnum
from db import models
from db.session import get_db

router = APIRouter(prefix="/api/parking", tags=["parking"])

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

    if user.role not in (RoleEnum.admin, RoleEnum.operator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Management staff only."
        )
    return AdminOut.model_validate(user)


def verify_management_staff(current_user: AdminOut = Depends(get_current_admin_user)):
    if current_user.role not in (RoleEnum.admin, RoleEnum.operator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Management staff only."
        )
    return current_user

@router.get("/auth/verify-camera")
def check_camera_access(_=Depends(verify_camera_staff)):
    return Response(status_code=status.HTTP_200_OK)


@router.get("/snapshot/latest", response_model=ParkingSnapshotResponse, status_code=status.HTTP_200_OK)
def get_latest_snapshot(
    parking_service: ParkingService = Depends(get_parking_service),
):
    return parking_service.get_latest_snapshot()


@router.get("/snapshot2/latest", response_model=ParkingSnapshotResponse, status_code=status.HTTP_200_OK)
def get_latest_snapshot2(
    parking_service: ParkingService = Depends(get_parking_service),
):
    return parking_service.get_latest_snapshot2()


@router.get("/inference")
def get_parking1_inference(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff)
):
    image_bytes = parking_service.infer_parking1_snapshot()
    return Response(content=image_bytes, media_type="image/jpeg")


@router.get("/inference2")
def get_parking2_inference(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff)
):
    image_bytes = parking_service.infer_parking2_snapshot()
    return Response(content=image_bytes, media_type="image/jpeg")


@router.get("/open")
def get_open_gate(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff),
):
    return parking_service.open_gate()


@router.get("/exit-gate/status")
def get_exit_gate_status(
    parking_service: ParkingService = Depends(get_parking_service),
    _: AdminOut = Depends(verify_management_staff)
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