from pydantic import BaseModel, field_validator
from datetime import datetime
import pytz

class EntryRecordBase(BaseModel):
    plate_number: str
    plate_image_url: str
    timestamp: datetime

class EntryRecordCreate(EntryRecordBase):
    pass

class EntryRecord(EntryRecordBase):
    id: int

    @field_validator('timestamp')
    def convert_to_bkk(cls, v):
        if v.tzinfo is None:
            v = pytz.utc.localize(v)
        bkk_tz = pytz.timezone('Asia/Bangkok')
        return v.astimezone(bkk_tz)

    class Config:
        from_attributes = True


class WeeklyUsage(BaseModel):
    date: str
    count: int
