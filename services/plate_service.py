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
        items = self.repo.get_plate_with_user(page, limit)
        return items, self.repo.count_plates()
    
    def create_plate(self, current_user: Admin, payload:LicensePlateCreate):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(status_code=401, detail="You are not authorized to perform this action")
        if self.repo.find_plate_by_number(payload.plate_number):
            raise HTTPException(status_code=409, detail="A plate with this number already exists")
        return self.repo.create_plate(payload)

    def update_plate(self, plate_id: int, payload: LicensePlateUpdate, current_user: Admin):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(status_code=401, detail="Not authorized")
        plate = self.repo.find_plate_by_id(plate_id)
        if not plate:
            raise HTTPException(status_code=404, detail="License plate not found")
        if payload.plate_number is not None and payload.plate_number != plate.plate_number:
            existing = self.repo.find_plate_by_number(payload.plate_number)
            if existing and existing.id != plate_id:
                raise HTTPException(status_code=409, detail="A plate with this number already exists")
        return self.repo.update_plate(plate, payload)

    def delete_plate(self, plate_id: int, current_user: Admin):
        if current_user.role not in ("admin", "operator"):
            raise HTTPException(status_code=401, detail="Not authorized")
        plate = self.repo.find_plate_by_id(plate_id)
        if not plate:
            raise HTTPException(status_code=404, detail="License plate not found")
        return self.repo.delete_plate(plate)
