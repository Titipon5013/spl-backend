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

    def get_reply(self, user_message: str) -> str:
        print(f"Processing message: {user_message}")
        lang = "th" if self.is_thai(user_message) else "en"
        user_message_lower = user_message.lower()

        negative_keywords = ["เรือ", "เครื่องบิน", "มอไซ", "จักรยาน", "boat", "bike", "motorcycle"]
        if any(word in user_message_lower for word in negative_keywords):
            if lang == "th":
                return "ระบบเรารองรับเฉพาะที่จอดรถยนต์นะครับ 😅 สำหรับยานพาหนะอื่นต้องขออภัยด้วยครับ"
            else:
                return "CAMT parking is for cars only 😅. Sorry for other vehicles."

        # ดักจับคำถามเกี่ยวกับที่จอดรถโดยตรง
        parking_keywords = ["จอด", "ว่าง", "รถ", "เต็ม", "ที่", "park", "space", "available", "full", "lot", "camt"]
        is_asking_about_parking = any(keyword in user_message_lower for keyword in parking_keywords)

        if is_asking_about_parking:
            return self.calculate_eta(lot_id="CAMT_01", lang=lang)

        # --- ให้ Gemini ช่วยวิเคราะห์เจตนา (Hybrid AI Router) ---
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
                    return self.calculate_eta(lot_id="CAMT_01", lang=lang)
                else:
                    print("Gemini classified as NOT Parking Intent.")
            except Exception as e:
                print(f"Gemini Error: {e}")

        # --- ถ้าไม่ตรงกับอะไรเลย ให้ตอบกลับแบบ Default ---
        if lang == "th":
            return "ผมคือผู้ช่วย ParkPilot 🚗 รับหน้าที่ดูแลเรื่องที่จอดรถครับ หากต้องการเช็คที่ว่าง หรือแชร์โลเคชั่นให้ประเมินเวลาเดินทาง ถามผมได้เลยครับ!"
        else:
            return "I am ParkPilot 🚗, your parking assistant. Please ask me about parking availability or share your location for an ETA!"

    def calculate_eta(self, lot_id: str = "CAMT_01", lang: str = "th", travel_mins: int = 0) -> str:
        now = datetime.utcnow()

        model = ParkingSnapshot if lot_id == "CAMT_01" else ParkingSnapshot2
        latest = self.db.query(model).filter(model.lot_id == lot_id).order_by(model.timestamp.desc()).first()

        if not latest:
            print("Warning: No parking data found in the database.")
            return "ขออภัยครับ ตอนนี้ระบบยังไม่มีข้อมูล" if lang == "th" else "Sorry, parking data is not available at the moment."

        time_15_mins_ago = now - timedelta(minutes=15)
        past = self.db.query(model).filter(
            model.lot_id == lot_id, model.timestamp <= time_15_mins_ago
        ).order_by(model.timestamp.desc()).first()

        rate_per_min = 0.0
        mins_to_full = 9999
        if past and latest.occupied_spaces > past.occupied_spaces:
            diff = latest.occupied_spaces - past.occupied_spaces
            rate_per_min = diff / 15.0
            mins_to_full = latest.available_spaces / rate_per_min

        if latest.available_spaces > 0:
            if travel_mins > 0:
                # เคสที่ 1: เหลือที่จอดน้อยมาก (<= 3) และใช้เวลาเดินทางนาน (>= 10 นาที)
                if latest.available_spaces <= 3 and travel_mins >= 10:
                    if lang == "th":
                        return f"คุณจะใช้เวลาเดินทาง {travel_mins} นาที แต่ตอนนี้เหลือที่จอดเพียง {latest.available_spaces} ที่ โอกาสเต็มก่อนไปถึงมีสูงมากครับ แนะนำให้เตรียมที่จอดสำรองไว้ด้วยนะครับ"
                    else:
                        return f"Your travel time is {travel_mins} mins, but only {latest.available_spaces} spaces are left. It is highly likely to be full upon arrival. Please consider a backup parking plan."

                # เคสที่ 2: อัตราการเติมเต็มเร็วกว่าเวลาเดินทาง (ที่จอดจะเต็มก่อนไปถึง)
                elif mins_to_full < travel_mins:
                    if lang == "th":
                        return f"คุณจะใช้เวลาเดินทาง {travel_mins} นาที แต่จากแนวโน้มตอนนี้คาดว่าที่จอดจะเต็มในอีก {int(mins_to_full)} นาทีครับ อาจจะไม่ทัน แนะนำให้หาที่จอดสำรองครับ"
                    else:
                        return f"Travel time is {travel_mins} mins, but spaces are filling up fast and expected to be full in {int(mins_to_full)} mins. You might not make it. Consider alternative parking."

                # เคสที่ 3: เวลาเหลือเฟือและที่จอดเพียงพอ
                else:
                    if lang == "th":
                        return f"คุณจะใช้เวลาเดินทาง {travel_mins} นาที ลานจอดยังมีที่ว่าง ({latest.available_spaces} คัน) น่าจะทันสบายๆ ครับ ขับรถปลอดภัยนะครับ!"
                    else:
                        return f"Travel time is {travel_mins} mins. There should still be spaces available ({latest.available_spaces} left). Drive safely!"

            # กรณีไม่ได้ส่ง Location (แค่ถามว่าว่างไหม)
            if rate_per_min > 0 and mins_to_full < 60:
                return f"มีที่ว่าง {latest.available_spaces} คัน (รถกำลังทยอยเข้าจอด คาดว่าจะเต็มในอีกประมาณ {int(mins_to_full)} นาที) รีบมานะครับ!" if lang == "th" else f"There are {latest.available_spaces} spaces left. It's filling up (Expected to be full in ~{int(mins_to_full)} mins). Hurry up!"

            return f"ตอนนี้มีที่ว่าง {latest.available_spaces} คัน จอดได้สบายๆ ครับ!" if lang == "th" else f"There are {latest.available_spaces} spaces left. Plenty of room!"

        # ------------------------------------------------------------------
        # กรณีที่จอดเต็ม 100% (ประเมินเวลาที่น่าจะว่าง)
        # ------------------------------------------------------------------
        end_date = now
        start_date = end_date - timedelta(days=7)
        trends_data = self.analytics_service.get_occupancy_trends(lot_id, start_date, end_date)

        current_hour = now.hour
        expected_free_time = None

        if trends_data and trends_data.trends:
            for trend in trends_data.trends:
                trend_hour = int(trend.time_label.split(" ")[1].split(":")[0])
                if trend_hour > current_hour and trend.average_occupancy < latest.total_spaces:
                    expected_free_time = f"{trend_hour}:00"
                    break

        if expected_free_time:
            return f"ตอนนี้ที่จอดรถเต็มครับ คาดว่าจะเริ่มว่างอีกทีตอน {expected_free_time} น." if lang == "th" else f"Parking is completely full 😢 Expected to be available around {expected_free_time}."

        return "ตอนนี้ที่จอดเต็มแน่นเลยครับ แนะนำให้หาที่จอดอื่นนะครับ" if lang == "th" else "Parking is fully occupied. Please find alternative parking."

    def calculate_travel_eta(self, lat: float, lng: float, lang: str = "th") -> str:
        print(f"Calculating travel ETA from ({lat}, {lng}) to CAMT")

        R = 6371
        dLat = math.radians(self.camt_lat - lat)
        dLon = math.radians(self.camt_lng - lng)
        a = math.sin(dLat / 2) * math.sin(dLat / 2) + math.cos(math.radians(lat)) * math.cos(
            math.radians(self.camt_lat)) * math.sin(dLon / 2) * math.sin(dLon / 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance_km = R * c

        travel_mins = int((distance_km * 1.3) * 2)
        if travel_mins < 1: travel_mins = 1

        print(f"Estimated distance: {distance_km:.2f} km, Travel time: {travel_mins} mins")

        # ส่งค่า lang ต่อไปให้ฟังก์ชัน ETA เพื่อให้บอทตอบกลับด้วยภาษาที่ถูกต้อง
        return self.calculate_eta(lot_id="CAMT_01", lang=lang, travel_mins=travel_mins)