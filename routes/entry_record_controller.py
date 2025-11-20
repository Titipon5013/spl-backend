from typing import List, Optional
from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, HTTPException
from schemas.entry_record import EntryRecord, WeeklyUsage
from services.entry_record_service import EntryRecordService
from services.dependencies import get_entry_record_service
from datetime import date

router = APIRouter(prefix="/api", tags=["entry-records"])

@router.get("/entry-records", response_model=List[EntryRecord])
def get_all_entry_records(
    entry_record_service: EntryRecordService = Depends(get_entry_record_service),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    return entry_record_service.get_all_entry_records(start_date=start_date, end_date=end_date)

@router.get("/entry-records/weekly-usage", response_model=List[WeeklyUsage])
def get_weekly_usage(
    entry_record_service: EntryRecordService = Depends(get_entry_record_service),
):
    return entry_record_service.get_weekly_usage()

@router.put("/entry-records/{entry_id}", response_model=EntryRecord)
def update_entry_record(
    entry_id: int,
    plate_number: str = Form(...),
    file: Optional[UploadFile] = File(None),
    entry_record_service: EntryRecordService = Depends(get_entry_record_service),
):
    try:
        return entry_record_service.update_entry_record(
            entry_id=entry_id,
            plate_number=plate_number,
            file=file,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/entry-records/{entry_id}", status_code=204)
def delete_entry_record(
    entry_id: int,
    entry_record_service: EntryRecordService = Depends(get_entry_record_service),
):
    try:
        entry_record_service.delete_entry_record(entry_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Entry record deleted successfully"}
