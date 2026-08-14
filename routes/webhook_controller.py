import os
from fastapi import APIRouter, Request, Depends, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, LocationAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent
from sqlalchemy.orm import Session
from db.session import get_db
import services

print("👉 สรุป services ดึงมาจากไหน:", services.__file__)
from services.user_chatbot_service import ChatbotService

router = APIRouter()

user_channel_secret = os.getenv("USER_LINE_CHANNEL_SECRET", "")
user_channel_access_token = os.getenv("USER_LINE_ACCESS_TOKEN", "")

user_configuration = Configuration(access_token=user_channel_access_token)
user_parser = WebhookParser(user_channel_secret)

@router.post("/line/user")
async def user_line_webhook(request: Request, db: Session = Depends(get_db)):
    signature = request.headers.get("X-Line-Signature", "")

    body = await request.body()
    body_decode = body.decode("utf-8")

    try:
        events = user_parser.parse(body_decode, signature)
    except InvalidSignatureError:
        print("Error: Invalid signature. Please check your USER_LINE_CHANNEL_SECRET.")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"Error parsing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    with ApiClient(user_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        chatbot_service = ChatbotService(db)

        for event in events:
            if not isinstance(event, MessageEvent):
                continue

            reply_message = None

            if isinstance(event.message, TextMessageContent):
                user_msg = event.message.text
                print(f"Received Text: {user_msg}")

                reply_data = chatbot_service.get_reply(user_msg)

                if reply_data["type"] == "quick_reply_location":
                    quick_reply = QuickReply(
                        items=[
                            QuickReplyItem(
                                action=LocationAction(label="แชร์พิกัด 📍")
                            )
                        ]
                    )
                    reply_message = TextMessage(
                        text=reply_data["text"],
                        quick_reply=quick_reply
                    )
                else:
                    reply_message = TextMessage(text=reply_data["text"])

            elif isinstance(event.message, LocationMessageContent):
                lat = event.message.latitude
                lng = event.message.longitude
                print(f"Received Location: Lat={lat}, Lng={lng}")

                reply_text = chatbot_service.calculate_travel_eta(lat, lng)
                reply_message = TextMessage(text=reply_text)

            if reply_message:
                try:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[reply_message]
                        )
                    )
                except Exception as e:
                    print(f"Error sending reply to LINE: {e}")

    return "OK"