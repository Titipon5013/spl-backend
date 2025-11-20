from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status, Query
from pydantic import EmailStr
from schemas.request import LicensePlateUpdate, LicensePlateCreate
from db.models import Admin
from auth import dependencies
from services.plate_service import PlateService
from services.dependencies import get_plate_service
from helpers.s3_cloudfront import S3CloudFront
import os

router = APIRouter(tags=["License Plates"])

s3_cloudfront = S3CloudFront(
    os.getenv("AWS_ACCESS_KEY"),
    os.getenv("AWS_SECRET_ACCESS_KEY"),
    os.getenv("S3_REGION"),
    os.getenv("S3_BUCKET"),
    os.getenv("CLOUDFRONT_URL"),
)

@router.get("/api/plates")
async def get_plates(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    plate_service: PlateService = Depends(get_plate_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return plate_service.get_all_plates(current_user, page, limit)

@router.post("/api/plates")
def create_plate(
    email: EmailStr = Form(...),
    name: str = Form(...),
    plateNumber: str = Form(...),
    photo: UploadFile = File(...),
    plate_service: PlateService = Depends(get_plate_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    photo_url = s3_cloudfront.upload_file(photo.file, photo.filename)
    payload = LicensePlateCreate(
        user_email=email,
        username=name,
        plate_number=plateNumber,
        plate_image_url=photo_url,
    )
    return plate_service.create_plate(current_user, payload)

@router.put("/api/plates/{plate_id}")
async def update_plate(
    plate_id: int,
    plate_number: str = Form(...),
    user_email: EmailStr = Form(...),
    username: str = Form(...),
    file: UploadFile = File(None),
    plate_service: PlateService = Depends(get_plate_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    photo_url = None
    if file:
        photo_url = s3_cloudfront.upload_file(file.file, file.filename)

    payload = LicensePlateUpdate(
        plate_number=plate_number,
        user_email=user_email,
        username=username,
        plate_image_url=photo_url,
    )
    return plate_service.update_plate(plate_id, payload, current_user)


@router.delete("/api/plates/{plate_id}")
async def delete_plate(
    plate_id: int,
    plate_service: PlateService = Depends(get_plate_service),
    current_user: Admin = Depends(dependencies.get_current_admin_user),
):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return plate_service.delete_plate(plate_id, current_user)
