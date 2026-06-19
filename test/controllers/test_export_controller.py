from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from db.models import Admin, ParkingSnapshot
from enums import ApprovalStatus, AuthProvider, RoleEnum


@pytest.fixture
def approved_admin(db_session):
    admin = Admin(
        username="exporter",
        email="exporter@example.com",
        hashed_password="hashed",
        role=RoleEnum.admin,
        auth_provider=AuthProvider.local,
        approval_status=ApprovalStatus.approved,
        created_at=datetime.utcnow(),
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


def _auth_headers(admin_id: int):
    from auth.dependencies import create_access_token

    token = create_access_token({"user_id": admin_id, "role": RoleEnum.admin.value})
    return {"Authorization": f"Bearer {token}"}


def test_export_csv(client, db_session, approved_admin):
    now = datetime.utcnow()
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=now,
            available_spaces=20,
            total_spaces=30,
            occupied_spaces=10,
            occupacy_rate=33.3,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/analytics/export",
        params={
            "lot_id": "CAMT_01",
            "start_date": (now - timedelta(days=1)).isoformat(),
            "end_date": now.isoformat(),
            "export_format": "csv",
        },
        headers=_auth_headers(approved_admin.id),
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert b"ParkPilot Analytics Export" in response.content


def test_export_pdf(client, db_session, approved_admin):
    now = datetime.utcnow()
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=now,
            available_spaces=20,
            total_spaces=30,
            occupied_spaces=10,
            occupacy_rate=33.3,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/analytics/export",
        params={
            "lot_id": "CAMT_01",
            "start_date": (now - timedelta(days=1)).isoformat(),
            "end_date": now.isoformat(),
            "export_format": "pdf",
        },
        headers=_auth_headers(approved_admin.id),
    )
    assert response.status_code == 200
    assert "application/pdf" in response.headers["content-type"]
    assert response.content.startswith(b"%PDF")


@patch("services.report_scheduler._run_weekly_reports")
def test_trigger_weekly_report(mock_run, client, approved_admin):
    response = client.post(
        "/api/reports/trigger",
        headers=_auth_headers(approved_admin.id),
    )
    assert response.status_code == 200
    mock_run.assert_called_once()


def test_weekly_scheduler_dispatches_reports_to_approved_admins(db_session, approved_admin):
    from services import report_scheduler

    export_payloads = {
        "csv": (b"csv-report", "weekly-report.csv", "text/csv"),
        "pdf": (b"%PDF-report", "weekly-report.pdf", "application/pdf"),
    }

    with patch.object(
        report_scheduler.ExportService,
        "export_analytics",
        side_effect=lambda _lot_id, _start_date, _end_date, export_format: export_payloads[export_format],
    ) as mock_export, patch.object(
        report_scheduler.EmailService,
        "send_weekly_report",
    ) as mock_send:
        report_scheduler._run_weekly_reports()

    assert mock_export.call_count == 4
    mock_send.assert_any_call(approved_admin.email, b"csv-report", b"%PDF-report")
    assert mock_send.call_count == 2


def test_start_report_scheduler_registers_weekly_cron_job(monkeypatch):
    from services import report_scheduler

    class FakeScheduler:
        def __init__(self):
            self.jobs = []
            self.started = False

        def add_job(self, func, **kwargs):
            self.jobs.append((func, kwargs))

        def start(self):
            self.started = True

        def shutdown(self, wait=False):
            self.started = False

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(report_scheduler, "_scheduler", None)
    monkeypatch.setattr(report_scheduler, "BackgroundScheduler", lambda: fake_scheduler)
    monkeypatch.setenv("WEEKLY_REPORT_DAY", "fri")
    monkeypatch.setenv("WEEKLY_REPORT_HOUR", "9")
    monkeypatch.setenv("WEEKLY_REPORT_MINUTE", "30")

    scheduler = report_scheduler.start_report_scheduler()

    assert scheduler is fake_scheduler
    assert fake_scheduler.started is True
    assert fake_scheduler.jobs == [
        (
            report_scheduler._run_weekly_reports,
            {
                "trigger": "cron",
                "day_of_week": "fri",
                "hour": 9,
                "minute": 30,
                "id": "weekly_parkpilot_report",
                "replace_existing": True,
            },
        )
    ]

    report_scheduler.stop_report_scheduler()
