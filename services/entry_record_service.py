from typing import List, Optional
from fastapi import UploadFile
from repository.ientry_record_repository import IEntryRecordRepository
from schemas.entry_record import EntryRecord, WeeklyUsage
from datetime import date
from helpers.s3_cloudfront import S3CloudFront
import os

class EntryRecordService:
    def __init__(self, entry_record_repository: IEntryRecordRepository):
        self.entry_record_repository = entry_record_repository
        self.s3_cloudfront = S3CloudFront(
            os.getenv("AWS_ACCESS_KEY"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("S3_REGION"),
            os.getenv("S3_BUCKET"),
            os.getenv("CLOUDFRONT_URL"),
        )

    def get_all_entry_records(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[EntryRecord]:
        db_entry_records = self.entry_record_repository.get_all_entry_records(start_date=start_date, end_date=end_date)
        return [EntryRecord.from_orm(rec) for rec in db_entry_records]

    def update_entry_record(self, entry_id: int, plate_number: str, file: Optional[UploadFile] = None) -> EntryRecord:
        db_entry_record = self.entry_record_repository.get_entry_record_by_id(entry_id)
        if not db_entry_record:
            raise Exception("Entry record not found")

        if file:
            if db_entry_record.plate_image_url: # type: ignore
                old_filename = db_entry_record.plate_image_url.split("/")[-1]
                self.s3_cloudfront.delete_file(old_filename)

            file_url = self.s3_cloudfront.upload_file(file.file, file.filename)
            db_entry_record.plate_image_url = file_url # type: ignore

        db_entry_record.plate_number = plate_number # type: ignore

        updated_record = self.entry_record_repository.update_entry_record(db_entry_record)
        return EntryRecord.from_orm(updated_record)

    def delete_entry_record(self, entry_id: int) -> None:
        db_entry_record = self.entry_record_repository.get_entry_record_by_id(entry_id)
        if not db_entry_record:
            raise Exception("Entry record not found")

        if db_entry_record.plate_image_url: # type: ignore
            filename = db_entry_record.plate_image_url.split("/")[-1]
            self.s3_cloudfront.delete_file(filename)

        self.entry_record_repository.delete_entry_record(entry_id)

    def get_weekly_usage(self) -> List[WeeklyUsage]:
        return self.entry_record_repository.get_last_7_days_entry_records()
