import os
import math
import json
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from services.analytics_service import AnalyticsService
from db.models import ParkingSnapshot, ParkingSnapshot2


class ChatbotService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

        self.camt_lat = 18.801092335425654
        self.camt_lng = 98.95082184123963

        self.agent_api_key = os.getenv("CLOUD_API_KEY")
        self.agent_endpoint = os.getenv("AGENT_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions")

    def is_thai(self, text: str) -> bool:
        return any('\u0E00' <= c <= '\u0E7F' for c in text)

    def _get_tools_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "check_parking_status",
                    "description": "ใช้ตรวจสอบสถานะที่จอดรถ ถ้าผู้ใช้ถามถึงที่จอดรถ ว่างไหม เต็มหรือยัง หรือถามเวลาเดินทาง",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {
                                "type": "string",
                                "description": "รหัสลานจอด (ใช้ CAMT_01 เสมอ)"
                            },
                            "travel_mins": {
                                "type": "integer",
                                "description": "เวลาเดินทางโดยประมาณ (นาที) ค่าเริ่มต้นคือ 0"
                            }
                        },
                        "required": ["lot_id"]
                    }
                }
            }
        ]

    def get_reply(self, user_message: str) -> dict:
        print(f"Processing message: {user_message}")
        lang = "th" if self.is_thai(user_message) else "en"
        user_message_lower = user_message.strip().lower()

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

        negative_keywords = ["เรือ", "เครื่องบิน", "มอไซ", "จักรยาน", "boat", "bike", "motorcycle"]
        if any(word in user_message_lower for word in negative_keywords):
            reply_text = "ระบบเรารองรับเฉพาะที่จอดรถยนต์นะครับ 😅 สำหรับยานพาหนะอื่นต้องขออภัยด้วยครับ" if lang == "th" else "Parking is for cars only 😅. Sorry for other vehicles."
            return {"type": "text", "text": reply_text}

        parking_keywords = ["จอด", "ว่าง", "รถ", "เต็ม", "ที่", "park", "space", "available", "full", "lot", "camt"]
        is_asking_about_parking = any(keyword in user_message_lower for keyword in parking_keywords)

        if is_asking_about_parking:
            return {"type": "text", "text": self.calculate_eta(lot_id="CAMT_01", lang=lang)}

        if self.agent_api_key:
            try:
                print("Sending message to OpenRouter Agent...")
                headers = {
                    "Authorization": f"Bearer {self.agent_api_key}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system",
                         "content": "คุณคือผู้ช่วย ParkPilot ตอบคำถามสั้นๆ สุภาพ ถ้าถามเรื่องที่จอดรถให้เรียกใช้ Tool ทันที"},
                        {"role": "user", "content": user_message}
                    ],
                    "tools": self._get_tools_schema(),
                    "tool_choice": "auto"
                }

                response = requests.post(self.agent_endpoint, headers=headers, json=payload, timeout=15)
                response.raise_for_status()
                ai_data = response.json()

                response_message = ai_data['choices'][0]['message']

                if 'tool_calls' in response_message and response_message['tool_calls']:
                    for tool_call in response_message['tool_calls']:
                        if tool_call['function']['name'] == "check_parking_status":
                            try:
                                arguments = json.loads(tool_call['function']['arguments'])
                            except json.JSONDecodeError:
                                arguments = {}

                            lot_id = arguments.get("lot_id", "CAMT_01")
                            travel_mins = arguments.get("travel_mins", 0)

                            print(f"Agent routed to check_parking_status (lot_id={lot_id}, travel_mins={travel_mins})")
                            return {"type": "text",
                                    "text": self.calculate_eta(lot_id=lot_id, lang=lang, travel_mins=travel_mins)}

                elif 'content' in response_message and response_message['content']:
                    print("Agent replied normally.")
                    return {"type": "text", "text": response_message['content']}

            except Exception as e:
                print(f"Agent Router Error: {e}")

        default_th = "ผมคือผู้ช่วย ParkPilot 🚗 รับหน้าที่ดูแลเรื่องที่จอดรถครับ หากต้องการเช็คที่ว่าง หรือแชร์โลเคชั่นให้ประเมินเวลาเดินทาง ถามผมได้เลยครับ!"
        default_en = "I am your parking assistant 🚗. Please ask me about parking availability or share your location for an ETA!"
        return {"type": "text", "text": default_th if lang == "th" else default_en}

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
                if latest.available_spaces <= 3 and travel_mins >= 10:
                    if lang == "th":
                        return f"คุณจะใช้เวลาเดินทาง {travel_mins} นาที แต่ตอนนี้เหลือที่จอดเพียง {latest.available_spaces} ที่ โอกาสเต็มก่อนไปถึงมีสูงมากครับ แนะนำให้เตรียมที่จอดสำรองไว้ด้วยนะครับ"
                    else:
                        return f"Your travel time is {travel_mins} mins, but only {latest.available_spaces} spaces are left. It is highly likely to be full upon arrival. Please consider a backup parking plan."

                elif mins_to_full < travel_mins:
                    if lang == "th":
                        return f"คุณจะใช้เวลาเดินทาง {travel_mins} นาที แต่จากแนวโน้มตอนนี้คาดว่าที่จอดจะเต็มในอีก {int(mins_to_full)} นาทีครับ อาจจะไม่ทัน แนะนำให้หาที่จอดสำรองครับ"
                    else:
                        return f"Travel time is {travel_mins} mins, but spaces are filling up fast and expected to be full in {int(mins_to_full)} mins. You might not make it. Consider alternative parking."

                else:
                    if lang == "th":
                        return f"คุณจะใช้เวลาเดินทาง {travel_mins} นาที ลานจอดยังมีที่ว่าง ({latest.available_spaces} คัน) น่าจะทันสบายๆ ครับ ขับรถปลอดภัยนะครับ!"
                    else:
                        return f"Travel time is {travel_mins} mins. There should still be spaces available ({latest.available_spaces} left). Drive safely!"

            if rate_per_min > 0 and mins_to_full < 60:
                return f"มีที่ว่าง {latest.available_spaces} คัน (รถกำลังทยอยเข้าจอด คาดว่าจะเต็มในอีกประมาณ {int(mins_to_full)} นาที) รีบมานะครับ!" if lang == "th" else f"There are {latest.available_spaces} spaces left. It's filling up (Expected to be full in ~{int(mins_to_full)} mins). Hurry up!"

            return f"ตอนนี้มีที่ว่าง {latest.available_spaces} คัน จอดได้สบายๆ ครับ!" if lang == "th" else f"There are {latest.available_spaces} spaces left. Plenty of room!"

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

        return self.calculate_eta(lot_id="CAMT_01", lang=lang, travel_mins=travel_mins)