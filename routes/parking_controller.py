from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from schemas.parking import ParkingSnapshotResponse
from services.dependencies import get_parking_service
from services.parking_service import ParkingService

router = APIRouter(prefix="/api/parking", tags=["parking"])


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
):
    image_bytes = parking_service.infer_parking1_snapshot()
    return Response(content=image_bytes, media_type="image/jpeg")

@router.get("/inference2")
def get_parking2_inference(
    parking_service: ParkingService = Depends(get_parking_service),
):
    image_bytes = parking_service.infer_parking2_snapshot()
    return Response(content=image_bytes, media_type="image/jpeg")

@router.get("/open")
def get_open_gate(
    parking_service: ParkingService = Depends(get_parking_service),
):
    return parking_service.open_gate()


@router.get("/exit-gate/status")
def get_exit_gate_status(
    parking_service: ParkingService = Depends(get_parking_service),
):
    return parking_service.get_exit_gate_status()


@router.post("/exit-gate/start")
def start_exit_gate_service(
    parking_service: ParkingService = Depends(get_parking_service),
):
    return parking_service.start_exit_gate_service()


@router.post("/exit-gate/stop")
def stop_exit_gate_service(
    parking_service: ParkingService = Depends(get_parking_service),
):
    return parking_service.stop_exit_gate_service()
