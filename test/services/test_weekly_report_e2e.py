"""End-to-end Feature 5 check: real dispatcher -> real SMTP -> captured mail.

Unlike the mocked scheduler tests in test_controllers/test_export_controller.py,
this one boots a local SMTP sink, runs report_scheduler._run_weekly_reports()
with the real ExportService/EmailService, and inspects the messages an admin
would actually receive.
"""

import email
import email.policy
import socketserver
import threading
from datetime import datetime, timedelta

from db.models import (
    Admin,
    EntryRecord,
    ParkingEventLog,
    ParkingSnapshot,
    ParkingSnapshot2,
    WeeklyLotMetric,
)
from enums import ApprovalStatus, AuthProvider, RoleEnum
from services import email_service, report_scheduler
from services.weekly_metrics_service import last_completed_utc_week


class SmtpSink:
    """Minimal SMTP capture server (no external dependency)."""

    def __init__(self):
        self.messages = []
        self.recipients = []
        sink = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"220 test-sink\r\n")
                in_data = False
                chunks = []
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    if in_data:
                        if line.rstrip(b"\r\n") == b".":
                            sink.messages.append(b"".join(chunks))
                            chunks = []
                            in_data = False
                            self.wfile.write(b"250 OK\r\n")
                        else:
                            # Undo SMTP dot-stuffing.
                            chunks.append(line[1:] if line.startswith(b"..") else line)
                        self.wfile.flush()
                        continue
                    command = line.decode("ascii", "replace").strip().upper()
                    if command.startswith(("EHLO", "HELO")):
                        self.wfile.write(b"250-test-sink\r\n250 OK\r\n")
                    elif command.startswith("RCPT TO"):
                        sink.recipients.append(line.decode("ascii", "replace").strip())
                        self.wfile.write(b"250 OK\r\n")
                    elif command.startswith("DATA"):
                        in_data = True
                        self.wfile.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    elif command.startswith("QUIT"):
                        self.wfile.write(b"221 Bye\r\n")
                        self.wfile.flush()
                        return
                    else:
                        self.wfile.write(b"250 OK\r\n")
                    self.wfile.flush()

        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_exc_info):
        self._server.shutdown()
        self._server.server_close()

    def parsed(self):
        return [
            email.message_from_bytes(raw, policy=email.policy.default)
            for raw in self.messages
        ]


def _add_admin(db_session, username, address, approval_status):
    admin = Admin(
        username=username,
        email=address,
        hashed_password="hashed",
        role=RoleEnum.admin,
        auth_provider=AuthProvider.local,
        approval_status=approval_status,
        created_at=datetime.utcnow(),
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def _seed_analytics(db_session):
    # ข้อมูลต้องอยู่ใน "สัปดาห์ที่เพิ่งจบ" (จันทร์-อาทิตย์ UTC) จึงจะถูกนับในรายงาน
    _, week_end = last_completed_utc_week()
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=week_end - timedelta(days=1, hours=1),
            available_spaces=6,
            total_spaces=30,
            occupied_spaces=24,
            occupacy_rate=80.0,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=week_end - timedelta(days=2),
            available_spaces=12,
            total_spaces=30,
            occupied_spaces=18,
            occupacy_rate=60.0,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    db_session.add(
        ParkingSnapshot2(
            lot_id="CAMT_02",
            timestamp=week_end - timedelta(days=1),
            available_spaces=20,
            total_spaces=30,
            occupied_spaces=10,
            occupacy_rate=33.33,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    # CAMT_01: 2 คัน, CAMT_02: 1 คัน ต่อสัปดาห์ + 1 คันนอกสัปดาห์ที่ต้องไม่ถูกนับ
    db_session.add(
        EntryRecord(
            plate_number="ABC1",
            plate_image_url="url",
            timestamp=week_end - timedelta(days=2),
            lot_id="CAMT_01",
        )
    )
    db_session.add(
        EntryRecord(
            plate_number="ABC2",
            plate_image_url="url",
            timestamp=week_end - timedelta(days=1),
            lot_id="CAMT_01",
        )
    )
    db_session.add(
        EntryRecord(
            plate_number="ABC3",
            plate_image_url="url",
            timestamp=week_end - timedelta(days=1),
            lot_id="CAMT_02",
        )
    )
    db_session.add(
        EntryRecord(
            plate_number="NEXT1",
            plate_image_url="url",
            timestamp=week_end + timedelta(hours=1),
            lot_id="CAMT_01",
        )
    )
    db_session.add(
        ParkingEventLog(
            lot_id="CAMT_01",
            spot_id="A1",
            is_occupied=True,
            timestamp=week_end - timedelta(days=2, hours=1),
        )
    )
    db_session.add(
        ParkingEventLog(
            lot_id="CAMT_01",
            spot_id="A1",
            is_occupied=False,
            timestamp=week_end - timedelta(days=2),
        )
    )
    db_session.commit()


def _point_email_service_at(monkeypatch, port):
    monkeypatch.setenv("EMAIL_DISABLED", "false")
    monkeypatch.setattr(email_service, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(email_service, "SMTP_PORT", port)
    monkeypatch.setattr(email_service, "SMTP_USER", "")
    monkeypatch.setattr(email_service, "SMTP_PASSWORD", "")
    monkeypatch.setattr(email_service, "SMTP_FROM", "parkpilot@test.local")
    monkeypatch.setattr(email_service, "SMTP_TIMEOUT", 5)


def _attachment_texts(message):
    attachments = {}
    for part in message.walk():
        filename = part.get_filename()
        if filename:
            attachments[filename] = part.get_payload(decode=True)
    return attachments


def _csv_sections(csv_text):
    """แยก CSV ที่รวมหลายลาน เป็น dict: lot_id -> list ของแถวใน section นั้น"""
    sections = {}
    current = None
    for line in csv_text.splitlines():
        parts = line.split(",")
        if len(parts) == 2 and parts[0] == "Lot ID":
            current = parts[1]
            sections[current] = []
        elif current is not None:
            sections[current].append(tuple(parts))
    return sections


def _body_text(message):
    for part in message.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode("utf-8", "replace")
    return ""


def test_weekly_reports_reach_approved_admin_over_real_smtp(db_session, monkeypatch):
    _add_admin(db_session, "approved", "weekly@example.com", ApprovalStatus.approved)
    _add_admin(db_session, "pending", "pending@example.com", ApprovalStatus.pending)
    _seed_analytics(db_session)

    with SmtpSink() as sink:
        _point_email_service_at(monkeypatch, sink.port)
        summary = report_scheduler._run_weekly_reports()

    assert summary == {"admins": 1, "emails_sent": 1, "emails_failed": 0, "errors": []}
    # one combined email per admin
    assert len(sink.messages) == 1
    assert all("weekly@example.com" in rcpt for rcpt in sink.recipients)
    assert not any("pending@example.com" in rcpt for rcpt in sink.recipients)

    message = sink.parsed()[0]
    assert message["To"] == "weekly@example.com"
    assert "All Lots" in message["Subject"]
    assert "2026-" in message["Subject"]
    assert "all parking lots" in _body_text(message)

    attachments = _attachment_texts(message)
    csv_name = next(name for name in attachments if name.endswith(".csv"))
    pdf_name = next(name for name in attachments if name.endswith(".pdf"))
    assert csv_name.startswith("parkpilot-weekly-")
    assert pdf_name.startswith("parkpilot-weekly-")
    assert attachments[pdf_name].startswith(b"%PDF")

    sections = _csv_sections(attachments[csv_name].decode())
    assert set(sections) == {"CAMT_01", "CAMT_02"}

    camt_01_rows = sections["CAMT_01"]
    assert ("Utilization %", "70.0") in camt_01_rows
    assert ("Peak Occupancy", "24") in camt_01_rows
    assert ("Vehicle Count", "2") in camt_01_rows
    assert ("Avg Dwell Time (min)", "60.0") in camt_01_rows
    assert ("A1", "50.0", "2") in camt_01_rows

    camt_02_rows = sections["CAMT_02"]
    assert ("Utilization %", "33.33") in camt_02_rows
    assert ("Vehicle Count", "1") in camt_02_rows

    # record รวมรายสัปดาห์ถูกจัดเก็บก่อนส่งเมล และตรงกับ KPI ใน CSV
    week_start, week_end = last_completed_utc_week()
    rows = db_session.query(WeeklyLotMetric).order_by(WeeklyLotMetric.lot_id).all()
    assert len(rows) == 2
    stored = {row.lot_id: row for row in rows}
    camt_01_row = stored["CAMT_01"]
    assert camt_01_row.week_start == week_start
    assert camt_01_row.week_end == week_end
    assert camt_01_row.utilization_percentage == 70.0
    assert camt_01_row.peak_occupancy == 24
    assert camt_01_row.vehicle_count == 2
    assert camt_01_row.avg_dwell_time_minutes == 60.0
    assert stored["CAMT_02"].vehicle_count == 1


def test_weekly_summary_is_upserted_and_covers_last_calendar_week(db_session, monkeypatch):
    _add_admin(db_session, "approved", "weekly@example.com", ApprovalStatus.approved)
    _seed_analytics(db_session)

    with SmtpSink() as sink:
        _point_email_service_at(monkeypatch, sink.port)
        first = report_scheduler._run_weekly_reports()
        second = report_scheduler._run_weekly_reports()

    assert first["emails_sent"] == 1
    assert second["emails_sent"] == 1
    assert len(sink.messages) == 2
    # trigger ซ้ำต้อง update แถวเดิม ไม่สร้างใหม่
    assert db_session.query(WeeklyLotMetric).count() == 2
    week_start, week_end = last_completed_utc_week()
    for row in db_session.query(WeeklyLotMetric).all():
        assert (row.week_start, row.week_end) == (week_start, week_end)


def test_weekly_report_smtp_failure_is_reported_not_raised(db_session, monkeypatch):
    _add_admin(db_session, "approved", "weekly@example.com", ApprovalStatus.approved)
    _seed_analytics(db_session)

    probe = socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler)
    closed_port = probe.server_address[1]
    probe.server_close()

    _point_email_service_at(monkeypatch, closed_port)

    summary = report_scheduler._run_weekly_reports()

    assert summary["admins"] == 1
    assert summary["emails_sent"] == 0
    assert summary["emails_failed"] == 1
    assert len(summary["errors"]) == 1
