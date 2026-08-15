import os
from fastapi import APIRouter, Request, Depends, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from sqlalchemy.orm import Session

from db.session import get_db

from services.admin_chatbot_service import AdminChatbotService

router = APIRouter()

admin_channel_secret = os.getenv("ADMIN_LINE_CHANNEL_SECRET", "")
admin_channel_access_token = os.getenv("ADMIN_LINE_ACCESS_TOKEN", "")

admin_configuration = Configuration(access_token=admin_channel_access_token)
admin_parser = WebhookParser(admin_channel_secret)


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

                if admin_msg.lower().strip() in ["/mute", "/unmute", "/settings"]:
                    reply_text = "🔧 ระบบจัดการแจ้งเตือน: (เตรียมรองรับฟีเจอร์ในอนาคต)"
                    reply_message = TextMessage(text=reply_text)

                else:
                    try:
                        reply_data = admin_chatbot_service.get_reply(admin_id=admin_id, user_message=admin_msg)
                        reply_message = TextMessage(text=reply_data.get("text", "ประมวลผลสำเร็จแต่ไม่มีข้อความตอบกลับ"))
                    except Exception as e:
                        # 3. Graceful Degradation (Error Handling)
                        print(f"Admin Service Error: {e}")
                        reply_message = TextMessage(
                            text="⚠️ ระบบประมวลผล AI หรือการเชื่อมต่อฐานข้อมูลขัดข้องชั่วคราวครับ\nกรุณาลองใหม่อีกครั้งในภายหลัง"
                        )

            if reply_message:
                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[reply_message]
                        )
                    )
                except Exception as e:
                    print(f"Error sending reply to Admin LINE: {e}")

    return "OK"