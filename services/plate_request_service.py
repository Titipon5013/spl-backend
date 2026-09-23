from fastapi import HTTPException, status
from repository.license_plate_request_repository import ImplLicensePlateRequestRepository
from schemas.request import LicensePlateRequestWithClient, RequestStatusUpdate, LicensePlateRequestCreate
from db.models import LicensePlate
from helpers.s3_cloudfront import S3CloudFront
from enums import RequestStatus
from typing import Optional
import os


# Allowed state transitions for a registration request. Decisions are reversible
# so an operator can revoke an accidental approval or re-approve a rejection,
# but no-op transitions (e.g. approved -> approved) are rejected.
_ALLOWED_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.pending: {RequestStatus.approved, RequestStatus.rejected},
    RequestStatus.approved: {RequestStatus.rejected},
    RequestStatus.rejected: {RequestStatus.approved},
}


class PlateRequestService:
    def __init__(self, repo: ImplLicensePlateRequestRepository):
        self.repo = repo
        self.s3_cloudfront = S3CloudFront(
            os.getenv("AWS_ACCESS_KEY"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("S3_REGION"),
            os.getenv("S3_BUCKET"),
            os.getenv("CLOUDFRONT_URL"),
        )
    
    def get_all_plate_requests(
        self,
        current_user,
        request_status: Optional[RequestStatus] = None,
        page: int = 1,
        limit: int = 10
    ) -> tuple[list[LicensePlateRequestWithClient], int]:
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="You are not authorized to perform this action"
            )
        
        plate_requests = self.repo.list_requests_with_user(status=request_status, page=page, limit=limit)
        
        items = [
            LicensePlateRequestWithClient(
                id=req.id, # type: ignore
                plate_number=req.plate_number, # type: ignore
                plate_image_url=req.plate_image_url, # type: ignore
                status=req.status.value,
                username=req.user.name,
                user_email=req.user.email
            )
            for req in plate_requests
        ]
        return items, self.repo.count_requests(status=request_status)

    def create_plate_request(self, form_data: dict):
        name = form_data["name"]
        email = form_data["email"]
        plate_number = form_data["plate_number"]
        plate_photo = form_data["plate_photo"]

        if self.repo.get_plate_by_number(plate_number):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A plate with this number is already registered",
            )
        if self.repo.get_pending_request_by_number(plate_number):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A pending request for this plate number already exists",
            )

        image_url = self.s3_cloudfront.upload_file(
            plate_photo.file,
            plate_photo.filename,
            prefix="plate-requests/",
            content_type=getattr(plate_photo, "content_type", None),
        )

        request_data = LicensePlateRequestCreate(
            username=name,
            user_email=email,
            plate_number=plate_number,
            plate_image_url=image_url,
            status=RequestStatus.pending
        )

        return self.repo.create_license_plate_request(request_data)
    
    def update_plate_status(self, req_id: int, new_status: RequestStatusUpdate, current_user):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized"
            )

        current = self.repo.get_request_by_id(req_id)
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

        target = new_status.status
        if target not in _ALLOWED_TRANSITIONS.get(current.status, set()):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Request cannot move from '{current.status.value}' to '{target.value}'",
            )

        # Approving must not collide with an existing plate for another record.
        if target == RequestStatus.approved:
            existing_plate = self.repo.get_plate_by_number(current.plate_number)
            if existing_plate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A plate with this number already exists",
                )

        updated_request = self.repo.update_req_status(req_id, new_status)

        if target == RequestStatus.approved:
            license_plate_data = LicensePlate(
                plate_number=updated_request.plate_number,
                user_id=updated_request.user_id,
                plate_image_url=updated_request.plate_image_url,
            )
            self.repo.add_plate(license_plate_data)
        else:
            # Revoking (or rejecting) removes any plate previously granted.
            existing_plate = self.repo.get_plate_by_number(updated_request.plate_number)
            if existing_plate:
                self.repo.delete_plate(existing_plate)

        return updated_request
