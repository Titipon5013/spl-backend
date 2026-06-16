import os
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from db.models import Admin
from db.session import Session
from enums import ApprovalStatus
from services.email_service import EmailService
from services.export_service import ExportService

_scheduler: BackgroundScheduler | None = None


def _run_weekly_reports():
    db = Session()
    try:
        export_service = ExportService(db)
        email_service = EmailService()
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        approved_admins = (
            db.query(Admin)
            .filter(Admin.approval_status == ApprovalStatus.approved)
            .all()
        )

        for admin in approved_admins:
            for lot_id in ("CAMT_01", "CAMT_02"):
                csv_bytes, _, _ = export_service.export_analytics(
                    lot_id, start_date, end_date, "csv"
                )
                pdf_bytes, _, _ = export_service.export_analytics(
                    lot_id, start_date, end_date, "pdf"
                )
                email_service.send_weekly_report(admin.email, csv_bytes, pdf_bytes)
    finally:
        db.close()


def start_report_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    cron_day = os.getenv("WEEKLY_REPORT_DAY", "mon")
    cron_hour = int(os.getenv("WEEKLY_REPORT_HOUR", "8"))
    cron_minute = int(os.getenv("WEEKLY_REPORT_MINUTE", "0"))

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_weekly_reports,
        trigger="cron",
        day_of_week=cron_day,
        hour=cron_hour,
        minute=cron_minute,
        id="weekly_parkpilot_report",
        replace_existing=True,
    )
    _scheduler.start()
    return _scheduler


def stop_report_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def trigger_weekly_reports_now():
    _run_weekly_reports()
