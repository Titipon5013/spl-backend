"""Feature 4 admin LINE webhook — link/mute/settings + MCP-backed chat."""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from sqlalchemy.orm import Session

from db.models import AdminAlertSubscription
from db.session import get_db
from services.admin_chatbot_service import DEFAULT_ALERT_TYPES, AdminChatbotService

router = APIRouter()

admin_channel_secret = os.getenv("ADMIN_LINE_CHANNEL_SECRET", "")
admin_channel_access_token = os.getenv("ADMIN_LINE_ACCESS_TOKEN", "")

admin_configuration = Configuration(access_token=admin_channel_access_token)
admin_parser = WebhookParser(admin_channel_secret)


def _link_secret() -> str:
    return os.getenv("ADMIN_LINE_LINK_SECRET", "").strip()


def _get_subscription(db: Session, line_user_id: str) -> AdminAlertSubscription | None:
    return (
        db.query(AdminAlertSubscription)
        .filter(AdminAlertSubscription.line_user_id == line_user_id)
        .first()
    )


def handle_admin_command(db: Session, line_user_id: str, text: str) -> str | None:
    """Handle /link /mute /unmute /settings. Returns reply text or None if not a command."""
    raw = text.strip()
    if not raw.startswith("/"):
        return None

    parts = raw.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/link":
        secret = _link_secret()
        if not secret:
            return "⚠️ Admin link secret is not configured on the server."
        if not arg or arg != secret:
            return "❌ Invalid link secret. Usage: `/link <secret>`"
        sub = _get_subscription(db, line_user_id)
        if sub is None:
            sub = AdminAlertSubscription(
                line_user_id=line_user_id,
                alert_types=DEFAULT_ALERT_TYPES,
                muted=False,
                linked_at=datetime.utcnow(),
            )
            db.add(sub)
        else:
            sub.linked_at = datetime.utcnow()
        db.commit()
        return (
            "✅ Linked. You can ask about occupancy, health, and anomalies.\n"
            "Commands: `/mute` `/unmute` `/settings`"
        )

    sub = _get_subscription(db, line_user_id)
    if sub is None:
        return (
            "บัญชีนี้ยังไม่ได้เชื่อมระบบแอดมิน\n"
            "พิมพ์ `/link <secret>` ก่อนใช้งานคำสั่งอื่น"
        )

    if command == "/mute":
        sub.muted = True
        db.commit()
        return "🔕 Alerts muted. You can still ask questions in chat."

    if command == "/unmute":
        sub.muted = False
        db.commit()
        return "🔔 Alerts unmuted. You will receive anomaly pushes again."

    if command == "/settings":
        status = "muted" if sub.muted else "active"
        return (
            f"⚙️ Admin alert settings\n"
            f"- line_user_id: {sub.line_user_id}\n"
            f"- push: {status}\n"
            f"- alert_types: {sub.alert_types}\n"
            f"- linked_at: {sub.linked_at.isoformat() if sub.linked_at else 'n/a'}"
        )

    return (
        "Unknown command. Available: `/link <secret>` `/mute` `/unmute` `/settings`"
    )


@router.post("/line/admin")
async def admin_line_webhook(request: Request, db: Session = Depends(get_db)):
    signature = request.headers.get("X-Line-Signature", "")

    body = await request.body()
    body_decode = body.decode("utf-8")

    try:
        events = admin_parser.parse(body_decode, signature)
    except InvalidSignatureError:
        print("Error: Invalid signature. Please check your ADMIN_LINE_CHANNEL_SECRET.")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"Error parsing admin webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    with ApiClient(admin_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        admin_chatbot_service = AdminChatbotService(db)

        for event in events:
            if not isinstance(event, MessageEvent):
                continue

            reply_message = None

            if isinstance(event.message, TextMessageContent):
                admin_msg = event.message.text
                admin_id = event.source.user_id
                print(f"Received Admin Text: {admin_msg} from {admin_id}")

                try:
                    command_reply = handle_admin_command(db, admin_id, admin_msg)
                    if command_reply is not None:
                        reply_message = TextMessage(text=command_reply)
                    else:
                        reply_data = admin_chatbot_service.get_reply(
                            admin_id=admin_id, user_message=admin_msg
                        )
                        reply_message = TextMessage(
                            text=reply_data.get(
                                "text", "ประมวลผลสำเร็จแต่ไม่มีข้อความตอบกลับ"
                            )
                        )
                except Exception as e:
                    print(f"Admin Service Error: {e}")
                    reply_message = TextMessage(
                        text=(
                            "⚠️ ระบบประมวลผล AI หรือการเชื่อมต่อฐานข้อมูลขัดข้องชั่วคราวครับ\n"
                            "กรุณาลองใหม่อีกครั้งในภายหลัง"
                        )
                    )

            if reply_message:
                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[reply_message],
                        )
                    )
                except Exception as e:
                    print(f"Error sending reply to Admin LINE: {e}")

    return "OK"
