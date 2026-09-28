"""Feature 5: สรุปตัวเลขรายสัปดาห์ต่อลาน เก็บลงตาราง weekly_lot_metrics

จุดประสงค์: ให้มี "record รวมของทั้งสัปดาห์" ถาวร ก่อนที่ข้อมูลดิบจะถูกเขียนทับ/
ลบสะสมไปเรื่อยๆ อีเมลรายงานรายสัปดาห์อ่านค่าจาก record นี้
"""

from datetime import datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from db.models import WeeklyLotMetric
from services.analytics_service import AnalyticsService

LOT_IDS = ("CAMT_01", "CAMT_02")


def last_completed_utc_week(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """คืน (week_start, week_end) ของสัปดาห์ที่เพิ่งจบล่าสุด เป็นเวลา UTC

    สัปดาห์คือ จันทร์ 00:00 → จันทร์ถัดไป 00:00 โดย week_end เป็นแบบ exclusive
    (เรียกวันจันทร์ก็ได้สัปดาห์ที่เพิ่งจบ, เรียกวันอื่นก็ยังได้สัปดาห์ที่จบล่าสุดเหมือนกัน)
    """
    now = now or datetime.utcnow()
    this_monday = datetime.combine(now.date() - timedelta(days=now.weekday()), time.min)
    return this_monday - timedelta(days=7), this_monday


def build_lot_metrics(
    db: Session, lot_id: str, start_date: datetime, end_date: datetime
) -> dict:
    return AnalyticsService(db).get_kpis(lot_id, start_date, end_date)


def record_weekly_metrics(
    db: Session,
    lot_id: str,
    week_start: datetime,
    week_end: datetime,
    metrics: Optional[dict] = None,
) -> WeeklyLotMetric:
    """Upsert สรุปสัปดาห์ของลานนี้ (เรียกซ้ำ/retry ได้ ไม่สร้างแถวเบิ้ล)"""
    if metrics is None:
        metrics = build_lot_metrics(db, lot_id, week_start, week_end)

    row = (
        db.query(WeeklyLotMetric)
        .filter(
            WeeklyLotMetric.lot_id == lot_id,
            WeeklyLotMetric.week_start == week_start,
        )
        .first()
    )
    if row is None:
        row = WeeklyLotMetric(lot_id=lot_id, week_start=week_start, week_end=week_end)
        db.add(row)

    row.week_end = week_end
    row.utilization_percentage = metrics["utilization_percentage"]
    row.peak_occupancy = metrics["peak_occupancy"]
    row.vehicle_count = metrics["vehicle_count"]
    row.avg_dwell_time_minutes = metrics["avg_dwell_time_minutes"]
    row.generated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row
