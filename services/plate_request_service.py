from fastapi import HTTPException, status
from repository.license_plate_request_repository import ImplLicensePlateRequestRepository
from schemas.request import LicensePlateRequestWithClient, RequestStatusUpdate, LicensePlateRequestCreate
from db.models import LicensePlate
from helpers.s3_cloudfront import S3CloudFront
from enums import RequestStatus
from typing import Optional
import os


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
    ) -> list[LicensePlateRequestWithClient]:
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="You are not authorized to perform this action"
            )
        
        plate_requests = self.repo.list_requests_with_user(status=request_status, page=page, limit=limit)
        
        return [
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

    def create_plate_request(self, form_data: dict):
        name = form_data["name"]
        email = form_data["email"]
        plate_number = form_data["plate_number"]
        plate_photo = form_data["plate_photo"]

        image_url = self.s3_cloudfront.upload_file(plate_photo.file, plate_photo.filename)

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
        updated_request = self.repo.update_req_status(req_id, new_status)

        if not updated_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

        # If approved, add to LicensePlate table
        if updated_request and new_status.status.lower() == "approved":
            license_plate_data = LicensePlate(
                plate_number=updated_request.plate_number,  
                user_id=updated_request.user_id,
                plate_image_url=updated_request.plate_image_url
            )
            self.repo.add_plate(license_plate_data)

        return updated_request
