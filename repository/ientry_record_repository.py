from abc import ABC, abstractmethod
from abc import ABC, abstractmethod
from typing import List, Optional
from db.models import EntryRecord
from datetime import date
from schemas.entry_record import WeeklyUsage

class IEntryRecordRepository(ABC):
    @abstractmethod
    def get_all_entry_records(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[EntryRecord]:
        pass

    @abstractmethod
    def get_entry_record_by_id(self, entry_id: int) -> Optional[EntryRecord]:
        pass

    @abstractmethod
    def update_entry_record(self, entry_record: EntryRecord) -> EntryRecord:
        pass

    @abstractmethod
    def delete_entry_record(self, entry_id: int) -> None:
        pass

    @abstractmethod
    def get_last_7_days_entry_records(self) -> List[WeeklyUsage]:
        pass
