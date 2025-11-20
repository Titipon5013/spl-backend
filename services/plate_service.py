from repository.plate_repository import PlateRepository
from db.models import Admin, User
from fastapi import HTTPException
from sqlalchemy.orm import Session
from schemas.request import LicensePlateCreate, LicensePlateUpdate

class PlateService:
    def __init__(self, repo: PlateRepository):
        self.repo = repo

    def get_all_plates(self, current_user: Admin, page: int = 1, limit: int = 10):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(status_code=401, detail="You are not authorized to perform this action")
        return self.repo.get_plate_with_user(page, limit)
    
    def create_plate(self, current_user: Admin, payload:LicensePlateCreate):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(status_code=401, detail="You are not authorized to perform this action")
        return self.repo.create_plate(payload)

    def update_plate(self, plate_id: int, payload: LicensePlateUpdate, current_user: Admin):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(status_code=401, detail="Not authorized")
        plate = self.repo.find_plate_by_id(plate_id)
        if not plate:
            raise HTTPException(status_code=404, detail="License plate not found")
        return self.repo.update_plate(plate, payload)

    def delete_plate(self, plate_id: int, current_user: Admin):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(status_code=401, detail="Not authorized")
        plate = self.repo.find_plate_by_id(plate_id)
        if not plate:
            raise HTTPException(status_code=404, detail="License plate not found")
        return self.repo.delete_plate(plate)
