import os
from fastapi import APIRouter, Request, Depends, HTTPException
from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage,
    QuickReply, QuickReplyItem, LocationAction, MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent, FollowEvent
from sqlalchemy.orm import Session
from db.session import get_db
import services

from services.user_chatbot_service import ChatbotService
from db.models import UserPreference

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
    except Exception:
        print("Error parsing user webhook")
        raise HTTPException(status_code=500, detail="Internal Server Error")

    with ApiClient(user_configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        chatbot_service = ChatbotService(db)

        for event in events:
            reply_message = None

            if isinstance(event, FollowEvent):
                quick_reply = QuickReply(items=[
                    QuickReplyItem(action=MessageAction(label="🇹🇭 ภาษาไทย", text="SET_LANG_TH")),
                    QuickReplyItem(action=MessageAction(label="🇬🇧 English", text="SET_LANG_EN"))
                ])
                reply_message = TextMessage(
                    text="ยินดีต้อนรับสู่ ParkPilot! กรุณาเลือกภาษา / Please select your language",
                    quick_reply=quick_reply
                )

            elif isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
                user_msg = event.message.text
                user_msg_lower = user_msg.strip().lower()
                user_id = event.source.user_id
                print(f"Received Text: {user_msg} from {user_id}")

                user_pref = db.query(UserPreference).filter_by(line_user_id=user_id).first()
                user_lang_db = user_pref.language if user_pref else None

                if user_msg_lower == "set_lang_th":
                    if user_pref:
                        user_pref.language = "th"
                    else:
                        db.add(UserPreference(line_user_id=user_id, language="th"))
                    db.commit()
                    reply_message = TextMessage(
                        text="ตั้งค่าภาษาไทยเรียบร้อยครับ 🚗\nสามารถเรียกใช้งานผ่านเมนูด้านล่างได้เลยครับ")

                elif user_msg_lower == "set_lang_en":
                    if user_pref:
                        user_pref.language = "en"
                    else:
                        db.add(UserPreference(line_user_id=user_id, language="en"))
                    db.commit()
                    reply_message = TextMessage(text="English language set 🚗\nYou can now use the menu below.")

                elif user_msg_lower in ["เช็คที่จอดรถ", "check parking", "check parking status"]:
                    final_lang = user_lang_db or ("th" if "เช็ค" in user_msg_lower else "en")
                    reply_text = chatbot_service.calculate_eta(lot_id="CAMT_01", lang=final_lang)
                    reply_message = TextMessage(text=reply_text)

                elif user_msg_lower in ["ประเมินเวลาเดินทาง", "eta", "estimate travel time"]:
                    final_lang = user_lang_db or ("th" if "ประเมิน" in user_msg_lower else "en")
                    quick_reply = QuickReply(items=[
                        QuickReplyItem(
                            action=LocationAction(label="แชร์พิกัด 📍" if final_lang == "th" else "Share Location 📍"))
                    ])
                    text_msg = "รบกวนแชร์ตำแหน่งปัจจุบันของคุณ เพื่อคำนวณเวลาเดินทางครับ 📍" if final_lang == "th" else "Please share your current location to calculate the ETA. 📍"
                    reply_message = TextMessage(text=text_msg, quick_reply=quick_reply)

                else:
                    reply_data = await chatbot_service.get_reply(user_msg, user_lang=user_lang_db)

                    if reply_data["type"] == "quick_reply_location":
                        label_text = "Share Location 📍" if user_lang_db == "en" else "แชร์พิกัด 📍"
                        quick_reply = QuickReply(
                            items=[QuickReplyItem(action=LocationAction(label=label_text))]
                        )
                        reply_message = TextMessage(
                            text=reply_data["text"],
                            quick_reply=quick_reply
                        )
                    else:
                        reply_message = TextMessage(text=reply_data["text"])

            elif isinstance(event, MessageEvent) and isinstance(event.message, LocationMessageContent):
                lat = event.message.latitude
                lng = event.message.longitude
                user_id = event.source.user_id
                print(f"Received Location message from {user_id}")

                user_pref = db.query(UserPreference).filter_by(line_user_id=user_id).first()
                user_lang_db = user_pref.language if user_pref else "th"

                try:
                    reply_text = chatbot_service.calculate_travel_eta(lat, lng, lang=user_lang_db)
                except ValueError:
                    reply_text = "พิกัดไม่ถูกต้อง กรุณาแชร์ตำแหน่งใหม่อีกครั้งครับ" if user_lang_db == "th" else "Invalid coordinates. Please share your location again."

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
                    print(f"Error sending user reply to LINE: {e}")

    return "OK"