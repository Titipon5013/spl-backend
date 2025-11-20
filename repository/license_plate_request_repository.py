from db.models import User
from typing import Optional
from repository.ilicense_plate_request_repository import LicensePlateRequestRepositoryInferface
from sqlalchemy.orm import Session, joinedload
from enums import RequestStatus
from db.models import LicensePlateRequest, LicensePlate
from schemas.request import LicensePlateRequestCreate, RequestStatusUpdate


class ImplLicensePlateRequestRepository(LicensePlateRequestRepositoryInferface):
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_by_email(self, email) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()
    
    def create_user_if_not_exists(self, name: str, email: str) -> User:
        user = self.get_user_by_email(email)
        if not user:
            user = User(name=name, email=email)
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
        return user

    def create_license_plate_request(self, request_data: LicensePlateRequestCreate) -> LicensePlateRequest:
        user = self.create_user_if_not_exists(request_data.username, request_data.user_email)
        request = LicensePlateRequest(
            user_id=user.id,
            plate_number=request_data.plate_number,
            plate_image_url=request_data.plate_image_url,
            status=request_data.status,
        )
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return request

    def list_requests_with_user(
        self,
        status: Optional[RequestStatus] = None,
        page: int = 1,
        limit: int = 10
    ) -> list[LicensePlateRequest]:
        query = self.db.query(LicensePlateRequest).options(joinedload(LicensePlateRequest.user))
        if status:
            query = query.filter(LicensePlateRequest.status == status)
        
        return query.offset((page - 1) * limit).limit(limit).all()
    
    def update_req_status(self, update_id, update_status: RequestStatusUpdate):
        to_update = self.db.query(LicensePlateRequest).filter(LicensePlateRequest.id == update_id).first()
        if to_update:
            to_update.status = update_status.status #type: ignore
            self.db.commit()
        return to_update

    def add_plate(self, plate: LicensePlate):
        self.db.add(plate)
        self.db.commit()
        self.db.refresh(plate)
        return plate
