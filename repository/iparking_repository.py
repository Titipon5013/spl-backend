from abc import ABC, abstractmethod
from typing import Optional
from db.models import ParkingSnapshot, ParkingSnapshot2
from schemas.parking import ParkingSnapshotCreate


class IParkingRepository(ABC):
    @abstractmethod
    def get_latest_snapshot(self) -> Optional[ParkingSnapshot]:
        pass

    @abstractmethod
    def get_latest_snapshot2(self) -> Optional[ParkingSnapshot2]:
        pass

    @abstractmethod
    def create_snapshot(self, snapshot: ParkingSnapshotCreate) -> ParkingSnapshot:
        pass
