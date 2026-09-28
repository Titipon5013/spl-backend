import os
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from db.models import Admin
from db.session import Session
from enums import ApprovalStatus
from services.anomaly_service import AnomalyService
from services.email_service import EmailService
from services.export_service import ExportService
from services.weekly_metrics_service import (
    LOT_IDS,
    build_lot_metrics,
    last_completed_utc_week,
    record_weekly_metrics,
)

_scheduler: BackgroundScheduler | None = None


def _run_weekly_reports() -> dict:
    db = Session()
    summary = {"admins": 0, "emails_sent": 0, "emails_failed": 0, "errors": []}
    try:
        export_service = ExportService(db)
        email_service = EmailService()
        week_start, week_end = last_completed_utc_week()
        # ใช้ window แบบ inclusive ถึงวินาทีสุดท้ายของวันอาทิตย์ กันนับซ้ำข้ามสัปดาห์
        report_end = week_end - timedelta(seconds=1)
        approved_admins = (
            db.query(Admin)
            .filter(Admin.approval_status == ApprovalStatus.approved)
            .all()
        )
        summary["admins"] = len(approved_admins)

        # เก็บ record รวมของทั้งสัปดาห์ (ต่อลาน) ก่อนส่งเมล
        lot_metrics = {}
        for lot_id in LOT_IDS:
            try:
                metrics = build_lot_metrics(db, lot_id, week_start, report_end)
                record_weekly_metrics(db, lot_id, week_start, week_end, metrics)
                lot_metrics[lot_id] = metrics
            except Exception as exc:
                summary["errors"].append(f"weekly summary {lot_id}: {exc}")

        for admin in approved_admins:
            if not admin.email:
                summary["errors"].append(f"admin id={admin.id}: no email address")
                continue
            if not lot_metrics:
                summary["emails_failed"] += 1
                summary["errors"].append(
                    f"{admin.email}: weekly summary unavailable for all lots"
                )
                continue
            try:
                csv_bytes, csv_filename, _ = export_service.export_combined_analytics(
                    list(lot_metrics.keys()),
                    week_start,
                    report_end,
                    "csv",
                    kpis_by_lot=lot_metrics,
                )
                pdf_bytes, pdf_filename, _ = export_service.export_combined_analytics(
                    list(lot_metrics.keys()),
                    week_start,
                    report_end,
                    "pdf",
                    kpis_by_lot=lot_metrics,
                )
                sent = email_service.send_weekly_report(
                    admin.email,
                    week_start,
                    report_end,
                    attachments=[
                        (csv_filename, csv_bytes),
                        (pdf_filename, pdf_bytes),
                    ],
                )
            except Exception as exc:
                summary["emails_failed"] += 1
                summary["errors"].append(
                    f"{admin.email}: combined export failed: {exc}"
                )
                continue

            if sent:
                summary["emails_sent"] += 1
            else:
                summary["emails_failed"] += 1
                summary["errors"].append(
                    f"{admin.email}: send failed (see EmailService log)"
                )
    finally:
        db.close()

    print(
        f"[weekly-report] admins={summary['admins']} sent={summary['emails_sent']} "
        f"failed={summary['emails_failed']}"
    )
    for error in summary["errors"]:
        print(f"[weekly-report] error: {error}")
    return summary


def _run_anomaly_detection():
    """ตรวจจับความผิดปกติ (URS-13) แล้วแจ้งเตือนแอดมิน (URS-26 / SRS-48–SRS-49)"""
    db = Session()
    try:
        result = AnomalyService(db).detect_anomalies()
        if result["new_anomalies"] or result["resolved_anomalies"]:
            print(
                f"[anomaly-detector] new={result['new_anomalies']} "
                f"resolved={result['resolved_anomalies']} "
                f"open={result['open_anomalies']}"
            )
        from services.admin_notification_service import AdminNotificationService

        notify = AdminNotificationService(db).dispatch_new_anomaly_alerts()
        if notify["pushed"] or notify["failures"]:
            print(
                f"[admin-notify] pushed={notify['pushed']} "
                f"failures={notify['failures']} "
                f"dup={notify['skipped_dup']}"
            )
    except Exception as e:
        print(f"[anomaly-detector] failed: {e}")
        db.rollback()
    finally:
        db.close()


def start_report_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    cron_day = os.getenv("WEEKLY_REPORT_DAY", "mon")
    cron_hour = int(os.getenv("WEEKLY_REPORT_HOUR", "8"))
    cron_minute = int(os.getenv("WEEKLY_REPORT_MINUTE", "0"))
    anomaly_interval = int(os.getenv("ANOMALY_SCAN_INTERVAL_MINUTES", "5"))

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_weekly_reports,
        trigger="cron",
        day_of_week=cron_day,
        hour=cron_hour,
        minute=cron_minute,
        id="weekly_parkpilot_report",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        _run_anomaly_detection,
        trigger="interval",
        minutes=anomaly_interval,
        id="parkpilot_anomaly_detection",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    return _scheduler


def stop_report_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def trigger_weekly_reports_now():
    return _run_weekly_reports()


def trigger_anomaly_detection_now():
    _run_anomaly_detection()
