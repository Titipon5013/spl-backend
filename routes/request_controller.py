from fastapi import Depends, APIRouter, Query
from db.models import Admin
from schemas.request import LicensePlateRequestWithClient, RequestStatusUpdate
from auth import dependencies
from typing import List, Optional
from services.plate_request_service import PlateRequestService
from services.dependencies import get_plate_request_service
from enums import RequestStatus

request_router: APIRouter = APIRouter(tags=["Registeration requests"])

@request_router.get("/api/requests", response_model=List[LicensePlateRequestWithClient])
async def list_requests(
    status: Optional[RequestStatus] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    service: PlateRequestService = Depends(get_plate_request_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    return service.get_all_plate_requests(current_user, status, page, limit)

# request in context means license plate registration request
@request_router.put("/api/requests/{request_id}")
def update_request_status(
    request_id: int,
    payload: RequestStatusUpdate,
    service: PlateRequestService = Depends(get_plate_request_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    return service.update_plate_status(request_id, payload, current_user)
