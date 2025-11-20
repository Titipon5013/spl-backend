from fastapi import Depends
from sqlalchemy.orm import Session
from db.session import get_db
from repository.admin_repository import ImplAdminRepositoryInterface
from services.admin_service import AdminService
from repository.plate_repository import PlateRepository
from services.plate_service import PlateService
from repository.license_plate_request_repository import ImplLicensePlateRequestRepository
from services.plate_request_service import PlateRequestService
from services.parking_service import ParkingService
from repository.parking_repository import ParkingRepository
from repository.entry_record_repository import EntryRecordRepository
from services.entry_record_service import EntryRecordService

def get_entry_record_service(db: Session = Depends(get_db)) -> EntryRecordService:
    entry_record_repo = EntryRecordRepository(db)
    return EntryRecordService(entry_record_repo)

def get_parking_service(db: Session = Depends(get_db)) -> ParkingService:
    parking_repo = ParkingRepository(db)
    return ParkingService(parking_repo)

def get_admin_repo(db: Session = Depends(get_db)) -> ImplAdminRepositoryInterface:
    return ImplAdminRepositoryInterface(db)


def get_admin_service(db: Session = Depends(get_db)) -> AdminService:
    admin_repo = ImplAdminRepositoryInterface(db)
    return AdminService(admin_repo)

def get_plate_service(db: Session = Depends(get_db)) -> PlateService:
    plate_repo = PlateRepository(db)
    return PlateService(plate_repo)

def get_plate_request_service(db: Session = Depends(get_db)) -> PlateRequestService:
    plate_request_repo = ImplLicensePlateRequestRepository(db)
    return PlateRequestService(plate_request_repo)
