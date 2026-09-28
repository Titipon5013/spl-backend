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

from db.models import Admin, EntryRecord, ParkingEventLog, ParkingSnapshot, ParkingSnapshot2
from enums import ApprovalStatus, AuthProvider, RoleEnum
from services import email_service, report_scheduler


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
    now = datetime.utcnow()
    db_session.add(
        ParkingSnapshot(
            lot_id="CAMT_01",
            timestamp=now - timedelta(hours=1),
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
            timestamp=now - timedelta(hours=2),
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
            timestamp=now - timedelta(hours=1),
            available_spaces=20,
            total_spaces=30,
            occupied_spaces=10,
            occupacy_rate=33.33,
            confidence=0.9,
            processing_time_seconds=0.1,
        )
    )
    for hours in (1, 2, 3):
        db_session.add(
            EntryRecord(
                plate_number=f"ABC{hours}",
                plate_image_url="url",
                timestamp=now - timedelta(hours=hours),
            )
        )
    db_session.add(
        ParkingEventLog(
            lot_id="CAMT_01",
            spot_id="A1",
            is_occupied=True,
            timestamp=now - timedelta(hours=3),
        )
    )
    db_session.add(
        ParkingEventLog(
            lot_id="CAMT_01",
            spot_id="A1",
            is_occupied=False,
            timestamp=now - timedelta(hours=2),
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

    assert summary == {"admins": 1, "emails_sent": 2, "emails_failed": 0, "errors": []}
    assert len(sink.messages) == 2
    assert all("weekly@example.com" in rcpt for rcpt in sink.recipients)
    assert not any("pending@example.com" in rcpt for rcpt in sink.recipients)

    by_lot = {}
    for message in sink.parsed():
        assert message["To"] == "weekly@example.com"
        attachments = _attachment_texts(message)
        csv_name = next(name for name in attachments if name.endswith(".csv"))
        pdf_name = next(name for name in attachments if name.endswith(".pdf"))
        csv_text = attachments[csv_name].decode()
        lot_id = next(
            line.split(",")[1] for line in csv_text.splitlines() if line.startswith("Lot ID")
        )
        by_lot[lot_id] = (message, attachments, csv_text)
        assert lot_id in message["Subject"]
        assert lot_id in csv_name
        assert attachments[pdf_name].startswith(b"%PDF")

    camt_01_message, camt_01_attachments, camt_01_csv = by_lot["CAMT_01"]
    assert "CAMT_01" in _body_text(camt_01_message)
    assert ("Utilization %", "70.0") in [
        tuple(line.split(",")) for line in camt_01_csv.splitlines()
    ]
    assert ("Peak Occupancy", "24") in [
        tuple(line.split(",")) for line in camt_01_csv.splitlines()
    ]
    assert ("Vehicle Count", "3") in [
        tuple(line.split(",")) for line in camt_01_csv.splitlines()
    ]
    assert ("Avg Dwell Time (min)", "60.0") in [
        tuple(line.split(",")) for line in camt_01_csv.splitlines()
    ]
    assert any("CAMT_01" in name for name in camt_01_attachments)

    camt_02_message, _, camt_02_csv = by_lot["CAMT_02"]
    assert "CAMT_02" in camt_02_message["Subject"]
    assert ("Utilization %", "33.33") in [
        tuple(line.split(",")) for line in camt_02_csv.splitlines()
    ]


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
    assert summary["emails_failed"] == 2
    assert len(summary["errors"]) == 2
