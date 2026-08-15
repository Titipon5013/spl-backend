import os
import json
import requests
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

# Import Models และ Service ของคุณ
from db.models import ParkingSnapshot, ParkingSnapshot2
from services.analytics_service import AnalyticsService


class AdminChatbotService:
    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

        self.api_key = os.getenv("CLOUD_API_KEY")
        self.endpoint = os.getenv("AGENT_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")

        self.system_prompt = (
            "You are a strict Admin AI expert for the ParkPilot smart parking system at CAMT. "
            "CRITICAL RULES: "
            "1. LANGUAGE: You MUST respond in the EXACT SAME LANGUAGE that the user used. "
            "2. TERMINOLOGY: This is a PARKING LOT, NOT a hotel. Use terms like 'อัตราการเข้าจอด', 'จำนวนรถ', or 'ความหนาแน่น'. For Thai pronouns, use 'ผม'. "
            "3. LIMITATIONS: You ONLY have data for parking status, device health, and occupancy statistics. "
            "4. NO FINANCIAL DATA: You DO NOT have financial, revenue, or billing data. If asked about revenue, YOU MUST REFUSE politely. "
            "5. ZONE RESTRICTION: You ONLY manage 'CAMT_01'. If asked about Zone A, B, or C, clarify that you only monitor CAMT_01. "
            "6. NO HALLUCINATION: Base your answers STRICTLY on the JSON data returned by the tools."
        )

    def is_thai(self, text: str) -> bool:
        return any('\u0E00' <= c <= '\u0E7F' for c in text)

    def _clean_response_text(self, text: str) -> str:
        """
        ฟังก์ชันเสริม (วิธีที่ 2): ดักลบคำศัพท์โรงแรมที่ AI เผลอหลุดออกมา
        แล้วสับเปลี่ยนเป็นคำที่เกี่ยวกับการจอดรถทันทีก่อนส่งเข้า LINE
        """
        replacements = {
            "การเข้าพัก": "การเข้าจอด",
            "เข้าพัก": "จอดรถ",
            "ผู้เข้าพัก": "ผู้ใช้งาน",
            "อัตราการเข้าพัก": "อัตราการใช้พื้นที่จอดรถ"
        }
        for wrong_word, correct_word in replacements.items():
            text = text.replace(wrong_word, correct_word)
        return text

    def _get_admin_tools_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_parking_status",
                    "description": "ดึงสถานะลานจอดรถปัจจุบัน (Real-time)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {"type": "string", "description": "รหัสลานจอด (ใช้ CAMT_01 เสมอ)"}
                        },
                        "required": ["lot_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_device_health",
                    "description": "ตรวจสอบสถานะอุปกรณ์กล้อง ว่ายังออนไลน์อยู่หรือไม่",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {"type": "string", "description": "รหัสลานจอด (ใช้ CAMT_01 เสมอ)"}
                        },
                        "required": ["lot_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_parking_analytics",
                    "description": "ดึงข้อมูลสถิติความหนาแน่นของลานจอดรถ (ภาพรวม 7 วัน หรือระบุวันที่ได้)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {"type": "string", "description": "รหัสลานจอด (ใช้ CAMT_01 เสมอ)"},
                            "start_date": {"type": "string",
                                           "description": "(Optional) วันที่เริ่มต้น Format: YYYY-MM-DD"},
                            "end_date": {"type": "string", "description": "(Optional) วันที่สิ้นสุด Format: YYYY-MM-DD"}
                        },
                        "required": ["lot_id"]
                    }
                }
            }
        ]

    def _execute_tool(self, function_name: str, arguments: dict) -> str:
        lot_id = arguments.get("lot_id", "CAMT_01")
        model = ParkingSnapshot if lot_id == "CAMT_01" else ParkingSnapshot2
        now = datetime.utcnow()

        if function_name == "get_parking_status":
            latest = self.db.query(model).filter(model.lot_id == lot_id).order_by(model.timestamp.desc()).first()
            if not latest:
                return json.dumps({"error": "No data found"})
            return json.dumps({
                "lot_id": lot_id, "available": latest.available_spaces,
                "occupied": latest.occupied_spaces, "total": latest.total_spaces
            })

        elif function_name == "check_device_health":
            latest = self.db.query(model).filter(model.lot_id == lot_id).order_by(model.timestamp.desc()).first()
            if not latest:
                return json.dumps({"error": "No data found"})
            time_diff = now - latest.timestamp
            is_offline = time_diff > timedelta(minutes=5)
            return json.dumps({
                "lot_id": lot_id, "status": "Offline" if is_offline else "Online",
                "offline_minutes": int(time_diff.total_seconds() / 60) if is_offline else 0,
                "last_update": latest.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            })

        elif function_name == "get_parking_analytics":
            start_str = arguments.get("start_date")
            end_str = arguments.get("end_date")

            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(hour=0, minute=0,
                                                                              second=0) if start_str else now - timedelta(
                    days=7)
                end_date = datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59,
                                                                          second=59) if end_str else now
            except:
                start_date, end_date = now - timedelta(days=7), now

            trends_data = self.analytics_service.get_occupancy_trends(lot_id, start_date, end_date)

            if not trends_data or not trends_data.trends:
                return json.dumps({"status": "no_data", "message": "No data found in the selected range."})

            peak_trend = max(trends_data.trends, key=lambda x: x.average_occupancy)
            return json.dumps({
                "query_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
                "peak_time_label": peak_trend.time_label,
                "peak_average_occupancy": round(peak_trend.average_occupancy, 2)
            })

        return json.dumps({"error": "Unknown function"})

    def get_reply(self, admin_id: str, user_message: str) -> dict:
        print(f"[Admin] Processing message: {user_message} from {admin_id}")

        lang = "th" if self.is_thai(user_message) else "en"

        if not self.api_key:
            err_msg = "⚠️ ระบบ AI ยังไม่พร้อมใช้งาน (Missing API Key)" if lang == "th" else "⚠️ AI system is not ready (Missing API Key)."
            return {"type": "text", "text": err_msg}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost",
            "Content-Type": "application/json"
        }

        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dynamic_prompt = self.system_prompt + f"\n[Reference: Current date and time is {current_datetime}]"

        messages_history = [
            {"role": "system", "content": dynamic_prompt},
            {"role": "user", "content": user_message}
        ]

        payload = {
            "model": "meta-llama/llama-3.3-70b-instruct",
            "messages": messages_history,
            "tools": self._get_admin_tools_schema(),
            "tool_choice": "auto"
        }

        try:
            response = requests.post(self.endpoint, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            ai_data = response.json()
            response_message = ai_data['choices'][0]['message']

            if 'tool_calls' in response_message and response_message['tool_calls']:
                messages_history.append(response_message)

                for tool_call in response_message['tool_calls']:
                    function_name = tool_call['function']['name']
                    tool_call_id = tool_call['id']

                    try:
                        arguments = json.loads(tool_call['function']['arguments'])
                    except json.JSONDecodeError:
                        arguments = {}

                    print(f"[Admin] LLM Called Tool: {function_name} | Args: {arguments}")

                    raw_data = self._execute_tool(function_name, arguments)

                    messages_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": function_name,
                        "content": raw_data
                    })

                payload["messages"] = messages_history
                payload.pop("tools", None)
                payload.pop("tool_choice", None)

                response_step2 = requests.post(self.endpoint, headers=headers, json=payload, timeout=15)
                response_step2.raise_for_status()
                final_ai_message = response_step2.json()['choices'][0]['message']['content']

                cleaned_message = self._clean_response_text(final_ai_message)
                return {"type": "text", "text": cleaned_message}

            elif 'content' in response_message and response_message['content']:
                return {"type": "text", "text": self._clean_response_text(response_message['content'])}

        except Exception as e:
            print(f"Admin Agent LLM Error: {e}")
            err_msg = "⚠️ ระบบประมวลผลคำถามหรือการเชื่อมต่อขัดข้องชั่วคราวครับ" if lang == "th" else "⚠️ The system encountered a temporary error. Please try again."
            return {"type": "text", "text": err_msg}

        err_msg = "ระบบประมวลผลสำเร็จแต่ไม่มีข้อมูลที่ตรงกับคำถามครับ" if lang == "th" else "Processing successful, but no matching data was found."
        return {"type": "text", "text": err_msg}