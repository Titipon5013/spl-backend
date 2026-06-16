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
