import os
from fastapi import APIRouter, Request, Depends, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent
from sqlalchemy.orm import Session
from db.session import get_db
import services
print("👉 สรุป services ดึงมาจากไหน:", services.__file__)
# ✅ แก้บรรทัดนี้ ให้ดึงข้อมูลจากไฟล์ user_chatbot_service แทน
from services.user_chatbot_service import ChatbotService

router = APIRouter()

channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

configuration = Configuration(access_token=channel_access_token)
parser = WebhookParser(channel_secret)


@router.post("/line")
async def line_webhook(request: Request, db: Session = Depends(get_db)):
    signature = request.headers.get("X-Line-Signature", "")

    body = await request.body()
    body_decode = body.decode("utf-8")

    try:
        events = parser.parse(body_decode, signature)
    except InvalidSignatureError:
        print("Error: Invalid signature. Please check your LINE_CHANNEL_SECRET.")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"Error parsing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # 💡 คลาสนี้จะถูกดึงมาจากไฟล์ user_chatbot_service ตามที่เราแก้ด้านบนครับ
        chatbot_service = ChatbotService(db)

        for event in events:
            if not isinstance(event, MessageEvent):
                continue

            reply_text = ""

            if isinstance(event.message, TextMessageContent):
                user_msg = event.message.text
                print(f"Received Text: {user_msg}")
                reply_text = chatbot_service.get_reply(user_msg)

            elif isinstance(event.message, LocationMessageContent):
                lat = event.message.latitude
                lng = event.message.longitude
                print(f"Received Location: Lat={lat}, Lng={lng}")
                reply_text = chatbot_service.calculate_travel_eta(lat, lng)

            if reply_text:
                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=reply_text)]
                        )
                    )
                except Exception as e:
                    print(f"Error sending reply to LINE: {e}")

    return "OK"