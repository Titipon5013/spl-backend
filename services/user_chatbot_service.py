import os
import math
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from services.analytics_service import AnalyticsService
from db.models import ParkingSnapshot, ParkingSnapshot2
import google.generativeai as genai

class ChatbotService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

        # พิกัดคณะ CAMT
        self.camt_lat = 18.801092335425654
        self.camt_lng = 98.95082184123963

        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        else:
            self.model = None

    def is_thai(self, text: str) -> bool:
        return any('\u0E00' <= c <= '\u0E7F' for c in text)

    def get_reply(self, user_message: str) -> dict:
        print(f"Processing message: {user_message}")
        lang = "th" if self.is_thai(user_message) else "en"
        user_message_lower = user_message.strip().lower()

        # ---------------------------------------------------------
        # 1. ดักจับ Event จากปุ่ม Rich Menu (Priority สูงสุด)
        # ---------------------------------------------------------
        if user_message_lower == "เช็คที่จอดรถ":
            return {
                "type": "text",
                "text": self.calculate_eta(lot_id="CAMT_01", lang="th")
            }

        if user_message_lower == "ประเมินเวลาเดินทาง":
            return {
                "type": "quick_reply_location",
                "text": "รบกวนแชร์ตำแหน่งปัจจุบันของคุณ เพื่อให้ระบบคำนวณเวลาเดินทางไปลานจอดรถครับ 📍"
            }

        # ---------------------------------------------------------
        # 2. ดักจับ Keyword พื้นฐาน
        # ---------------------------------------------------------
        negative_keywords = ["เรือ", "เครื่องบิน", "มอไซ", "จักรยาน", "boat", "bike", "motorcycle"]
        if any(word in user_message_lower for word in negative_keywords):
            reply_text = "ระบบเรารองรับเฉพาะที่จอดรถยนต์นะครับ 😅 สำหรับยานพาหนะอื่นต้องขออภัยด้วยครับ" if lang == "th" else "Parking is for cars only 😅. Sorry for other vehicles."
            return {"type": "text", "text": reply_text}

        parking_keywords = ["จอด", "ว่าง", "รถ", "เต็ม", "ที่", "park", "space", "available", "full", "lot", "camt"]
        is_asking_about_parking = any(keyword in user_message_lower for keyword in parking_keywords)

        if is_asking_about_parking:
            return {"type": "text", "text": self.calculate_eta(lot_id="CAMT_01", lang=lang)}

        # ---------------------------------------------------------
        # 3. ให้ Gemini ช่วยวิเคราะห์เจตนา (Hybrid AI Router)
        # ---------------------------------------------------------
        if self.model:
            try:
                print("Unclear message, sending to Gemini for intent classification...")
                prompt = f"""
                คุณคือระบบวิเคราะห์เจตนา (Intent Classifier) สำหรับระบบที่จอดรถอัจฉริยะ
                ประโยคของผู้ใช้คือ: "{user_message}"
                คำถามนี้ผู้ใช้ต้องการสอบถามสถานะลานจอดรถยนต์ หรือประเมินเวลาเดินทางไปที่จอดรถ ใช่หรือไม่?
                ตอบแค่คำว่า "True" หรือ "False" เท่านั้น
                """
                response = self.model.generate_content(prompt)
                intent = response.text.strip().lower()

                if "true" in intent:
                    print("Gemini classified as Parking Intent!")
                    return {"type": "text", "text": self.calculate_eta(lot_id="CAMT_01", lang=lang)}
                else:
                    print("Gemini classified as NOT Parking Intent.")
            except Exception as e:
                print(f"Gemini Error: {e}")

        # ---------------------------------------------------------
        # 4. Fallback Default Response
        # ---------------------------------------------------------
        default_th = "ผมคือผู้ช่วย ParkPilot 🚗 รับหน้าที่ดูแลเรื่องที่จอดรถครับ หากต้องการเช็คที่ว่าง หรือแชร์โลเคชั่นให้ประเมินเวลาเดินทาง ถามผมได้เลยครับ!"
        default_en = "I am your parking assistant 🚗. Please ask me about parking availability or share your location for an ETA!"
        return {"type": "text", "text": default_th if lang == "th" else default_en}

    # (ฟังก์ชัน calculate_eta และ calculate_travel_eta ใช้โค้ดเดิมได้เลย)
    def calculate_eta(self, lot_id: str = "CAMT_01", lang: str = "th", travel_mins: int = 0) -> str:
        # ... (โค้ดเดิม) ...
        pass

    def calculate_travel_eta(self, lat: float, lng: float, lang: str = "th") -> str:
        # ... (โค้ดเดิม) ...
        pass