import io
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import qrcode

SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "parkpilot@camt.cmu.ac.th")
LINE_BOT_URL = os.getenv("LINE_BOT_URL", "https://line.me/R/ti/p/@parkpilot")


class EmailService:
    def send_line_qr_email(self, recipient: str, name: str) -> bool:
        qr_image = self._generate_qr_png(LINE_BOT_URL)
        body = (
            f"Hello {name},\n\n"
            "Your ParkPilot administrator access has been approved.\n"
            "Scan the attached QR code to connect with the LINE chatbot.\n\n"
            f"Or open: {LINE_BOT_URL}\n"
        )
        return self._send_email(
            recipient,
            "ParkPilot — LINE Chatbot Access",
            body,
            attachments=[("line-chatbot-qr.png", qr_image)],
        )

    def send_weekly_report(
        self, recipient: str, csv_bytes: bytes, pdf_bytes: bytes
    ) -> bool:
        body = (
            "Attached are your weekly ParkPilot performance reports (CSV and PDF).\n"
        )
        return self._send_email(
            recipient,
            "ParkPilot — Weekly Performance Report",
            body,
            attachments=[
                ("weekly-report.csv", csv_bytes),
                ("weekly-report.pdf", pdf_bytes),
            ],
        )

    def _generate_qr_png(self, url: str) -> bytes:
        qr = qrcode.make(url)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        return buffer.getvalue()

    def _send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        attachments: list[tuple[str, bytes]] | None = None,
    ) -> bool:
        if os.getenv("EMAIL_DISABLED", "false").lower() == "true":
            print(f"[EmailService] Skipped email to {recipient}: {subject}")
            return True

        message = MIMEMultipart()
        message["From"] = SMTP_FROM
        message["To"] = recipient
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        for filename, content in attachments or []:
            part = MIMEApplication(content, Name=filename)
            part["Content-Disposition"] = f'attachment; filename="{filename}"'
            message.attach(part)

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                if SMTP_USER:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, [recipient], message.as_string())
            return True
        except Exception as exc:
            print(f"[EmailService] Failed to send email: {exc}")
            return False
