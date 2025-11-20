from sqlalchemy.orm import Session, joinedload
from db.models import LicensePlate
from schemas.request import LicensePlateCreate, LicensePlateUpdate
from db.models import User

class PlateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_plate_with_user(self, page: int = 1, limit: int = 10):
        return self.db.query(LicensePlate).options(joinedload(LicensePlate.user)).offset((page - 1) * limit).limit(limit).all()

    def find_plate_by_id(self, plate_id: int):
        return self.db.query(LicensePlate).filter(LicensePlate.id == plate_id).first()

    def create_plate(self, payload: LicensePlateCreate):
        user = self.db.query(User).filter(User.email == payload.user_email).first()
        if not user:
            user = User(name=payload.username, email=payload.user_email)
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        
        plate = LicensePlate(plate_number=payload.plate_number, plate_image_url=payload.plate_image_url, user_id=user.id)
        self.db.add(plate)
        self.db.commit()
        self.db.refresh(plate)
        return plate

    def delete_plate(self, plate: LicensePlate):
        self.db.delete(plate)
        self.db.commit()
        return plate

    def update_plate(self, plate: LicensePlate, payload: LicensePlateUpdate):
        if payload.plate_number is not None:
            setattr(plate, 'plate_number', payload.plate_number)
        if payload.plate_image_url is not None:
            setattr(plate, 'plate_image_url', payload.plate_image_url)
        if payload.user_email is not None:
            user = self.db.query(User).filter(User.email == payload.user_email).first()
            if not user:
                # If user does not exist, create a new one
                new_username = payload.username if payload.username is not None else plate.user.name
                user = User(name=new_username, email=payload.user_email)
                self.db.add(user)
                self.db.commit()
                self.db.refresh(user)
            
            plate.user_id = user.id
            if payload.username is not None:
                setattr(user, 'name', payload.username)
        self.db.commit()
        self.db.refresh(plate)
        return self.db.query(LicensePlate).options(joinedload(LicensePlate.user)).filter(LicensePlate.id == plate.id).first()
