from typing import Optional
from sqlalchemy.orm import Session
from db.models import ParkingSnapshot, ParkingSnapshot2
from repository.iparking_repository import IParkingRepository
from schemas.parking import ParkingSnapshotCreate


class ParkingRepository(IParkingRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_latest_snapshot(self) -> Optional[ParkingSnapshot]:
        return self.db.query(ParkingSnapshot).order_by(ParkingSnapshot.timestamp.desc()).first()

    def get_latest_snapshot2(self) -> Optional[ParkingSnapshot2]:
        return self.db.query(ParkingSnapshot2).order_by(ParkingSnapshot2.timestamp.desc()).first()

    def create_snapshot(self, snapshot: ParkingSnapshotCreate) -> ParkingSnapshot:
        snapshot_dict = snapshot.model_dump()
        db_snapshot = ParkingSnapshot(**snapshot_dict)
        self.db.add(db_snapshot)
        self.db.commit()
        self.db.refresh(db_snapshot)
        return db_snapshot
