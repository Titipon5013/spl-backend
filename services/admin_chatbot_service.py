"""Feature 4 admin LINE chatbot — conversational queries via Feature 2 MCP tools."""

from __future__ import annotations

import json
import os
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from db.models import AdminAlertSubscription
from services.mcp_client import McpClient, McpClientError


# Push only hardware/feed health by default (matches dashboard System Health).
# stuck_slot per-spot alerts are noisy while the campus feed is paused/unstable.
DEFAULT_ALERT_TYPES = "device_offline"


class AdminChatbotService:
    def __init__(self, db: Session, mcp_client: McpClient | None = None):
        self.db = db
        self.mcp = mcp_client or McpClient()

        self.api_key = os.getenv("CLOUD_API_KEY")
        self.endpoint = os.getenv(
            "AGENT_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"
        )

        # Guardrail: LLMs often mistranslate English "occupancy" into hotel Thai
        # (เข้าพัก / ผู้เข้าพัก). We ban those tokens so replies stay parking-domain.
        self.system_prompt = (
            "You are a ParkPilot teammate chatting with CAMT parking admins on LINE. "
            "Sound like a real coworker: short, clear, warm — not a corporate bot. "
            "Match the admin's language (Thai or English). "
            "Domain is a parking lot only (ลานจอดรถ CAMT), never a hotel. "
            "If English tool fields say occupancy/occupied, in Thai say "
            "อัตราการเข้าจอด / จำนวนรถที่จอด / ช่องว่าง — "
            "never hotel words like เข้าพัก, ผู้เข้าพัก, อัตราการเข้าพัก "
            "(those appear when models mistranslate 'occupancy'). "
            "Talk only about occupancy, camera/board health, trends, and anomalies. "
            "Lots: CAMT_01 and CAMT_02 only. No revenue or billing. "
            "Use tool JSON as the only source of truth; if data is missing, say so plainly. "
            "Prefer 2–5 short lines or a tiny bullet list. "
            "Don't dump robotic labels (anomaly_id, severity: warning, raw ISO times) "
            "unless the admin asks. "
            "Good: 'กล้อง 2 หลุดไปประมาณ 10 นาทีแล้ว'. Bad: pasting the whole JSON."
        )

    def is_thai(self, text: str) -> bool:
        return any("\u0E00" <= c <= "\u0E7F" for c in text)

    def get_subscription(self, line_user_id: str) -> AdminAlertSubscription | None:
        return (
            self.db.query(AdminAlertSubscription)
            .filter(AdminAlertSubscription.line_user_id == line_user_id)
            .first()
        )

    def is_linked(self, line_user_id: str) -> bool:
        return self.get_subscription(line_user_id) is not None

    def _clean_response_text(self, text: str) -> str:
        replacements = {
            "การเข้าพัก": "การเข้าจอด",
            "เข้าพัก": "จอดรถ",
            "ผู้เข้าพัก": "ผู้ใช้งาน",
            "อัตราการเข้าพัก": "อัตราการใช้พื้นที่จอดรถ",
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
                    "description": "ดึงสถานะลานจอดรถปัจจุบัน (Real-time occupancy via MCP)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {
                                "type": "string",
                                "description": "รหัสลานจอด (CAMT_01 หรือ CAMT_02)",
                            }
                        },
                        "required": ["lot_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_device_health",
                    "description": "ตรวจสอบสถานะอุปกรณ์กล้องและบอร์ดผ่าน MCP get_system_health",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {
                                "type": "string",
                                "description": "รหัสลานจอด (CAMT_01 หรือ CAMT_02)",
                            }
                        },
                        "required": ["lot_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_parking_analytics",
                    "description": "ดึงสถิติความหนาแน่น (MCP analyze_occupancy_trends)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {
                                "type": "string",
                                "description": "รหัสลานจอด (CAMT_01 หรือ CAMT_02)",
                            },
                            "start_date": {
                                "type": "string",
                                "description": "(Optional) YYYY-MM-DD",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "(Optional) YYYY-MM-DD",
                            },
                        },
                        "required": ["lot_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_system_anomalies",
                    "description": "รายการความผิดปกติของระบบที่ยังไม่ได้รับการตรวจ (MCP)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "anomaly_type": {
                                "type": "string",
                                "description": (
                                    "Optional filter: stuck_slot, pipeline_inactive, "
                                    "device_offline"
                                ),
                            },
                            "include_reviewed": {
                                "type": "boolean",
                                "description": "รวมรายการที่ review แล้วหรือไม่",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "จำนวนสูงสุด 1-200",
                            },
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mark_anomaly_reviewed",
                    "description": "ทำเครื่องหมายว่าแอดมินได้ตรวจสอบ anomaly แล้ว (MCP)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "anomaly_id": {
                                "type": "integer",
                                "description": "รหัส anomaly จาก get_system_anomalies",
                            },
                            "reviewed_by": {
                                "type": "string",
                                "description": "อีเมลหรือชื่อแอดมินที่ตรวจสอบ",
                            },
                        },
                        "required": ["anomaly_id", "reviewed_by"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "find_available_slots",
                    "description": "รายการช่องจอดที่ว่างตอนนี้ (MCP)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "lot_id": {
                                "type": "string",
                                "description": "รหัสลานจอด (CAMT_01 หรือ CAMT_02)",
                            }
                        },
                        "required": ["lot_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_slot_status",
                    "description": "สถานะช่องจอดเดี่ยว (MCP)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "spot_id": {
                                "type": "string",
                                "description": "รหัสช่องจอด เช่น A1",
                            },
                            "lot_id": {
                                "type": "string",
                                "description": "รหัสลานจอด (CAMT_01 หรือ CAMT_02)",
                            },
                        },
                        "required": ["spot_id"],
                    },
                },
            },
        ]

    def _prepare_arguments(self, function_name: str, arguments: dict) -> dict:
        """Normalize LLM arguments into MCP tool arguments."""
        args = dict(arguments or {})
        if function_name in (
            "get_parking_status",
            "check_device_health",
            "get_parking_analytics",
            "find_available_slots",
            "check_slot_status",
            "get_dwell_time_stats",
        ):
            args.setdefault("lot_id", "CAMT_01")
        # Drop empty optional fields so MCP schema defaults apply
        return {k: v for k, v in args.items() if v is not None and v != ""}

    def _execute_tool(self, function_name: str, arguments: dict) -> str:
        try:
            prepared = self._prepare_arguments(function_name, arguments)
            result = self.mcp.call_tool(function_name, prepared)
            return json.dumps(result, ensure_ascii=False)
        except McpClientError as exc:
            return json.dumps({"error": str(exc)})

    def unlinked_reply(self, lang: str = "th") -> dict:
        if lang == "th":
            text = (
                "บัญชี LINE นี้ยังไม่ได้เชื่อมกับระบบแอดมิน ParkPilot\n"
                "พิมพ์ `/link <รหัสลับ>` เพื่อเชื่อมบัญชี แล้วจึงสอบถามสถานะลานจอดได้"
            )
        else:
            text = (
                "This LINE account is not linked to ParkPilot admin alerts.\n"
                "Send `/link <secret>` first, then ask about parking status."
            )
        return {"type": "text", "text": text}

    def get_reply(self, admin_id: str, user_message: str) -> dict:
        print(f"[Admin] Processing message: {user_message} from {admin_id}")
        lang = "th" if self.is_thai(user_message) else "en"

        if not self.is_linked(admin_id):
            return self.unlinked_reply(lang)

        if not self.api_key:
            err_msg = (
                "⚠️ ระบบ AI ยังไม่พร้อมใช้งาน (Missing API Key)"
                if lang == "th"
                else "⚠️ AI system is not ready (Missing API Key)."
            )
            return {"type": "text", "text": err_msg}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost",
            "Content-Type": "application/json",
        }

        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dynamic_prompt = (
            self.system_prompt
            + f"\n[Reference: Current date and time is {current_datetime}]"
        )

        messages_history = [
            {"role": "system", "content": dynamic_prompt},
            {"role": "user", "content": user_message},
        ]

        payload = {
            "model": "meta-llama/llama-3.3-70b-instruct",
            "messages": messages_history,
            "tools": self._get_admin_tools_schema(),
            "tool_choice": "auto",
        }

        try:
            response = requests.post(
                self.endpoint, headers=headers, json=payload, timeout=15
            )
            response.raise_for_status()
            ai_data = response.json()
            response_message = ai_data["choices"][0]["message"]

            if response_message.get("tool_calls"):
                messages_history.append(response_message)

                for tool_call in response_message["tool_calls"]:
                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call["id"]

                    try:
                        arguments = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        arguments = {}

                    print(
                        f"[Admin] LLM Called Tool: {function_name} | Args: {arguments}"
                    )
                    raw_data = self._execute_tool(function_name, arguments)

                    messages_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": function_name,
                            "content": raw_data,
                        }
                    )

                payload["messages"] = messages_history
                payload.pop("tools", None)
                payload.pop("tool_choice", None)

                response_step2 = requests.post(
                    self.endpoint, headers=headers, json=payload, timeout=15
                )
                response_step2.raise_for_status()
                final_ai_message = response_step2.json()["choices"][0]["message"][
                    "content"
                ]

                cleaned_message = self._clean_response_text(final_ai_message)
                return {"type": "text", "text": cleaned_message}

            if response_message.get("content"):
                return {
                    "type": "text",
                    "text": self._clean_response_text(response_message["content"]),
                }

        except Exception as e:
            print(f"Admin Agent LLM Error: {e}")
            err_msg = (
                "⚠️ ระบบประมวลผลคำถามหรือการเชื่อมต่อขัดข้องชั่วคราวครับ"
                if lang == "th"
                else "⚠️ The system encountered a temporary error. Please try again."
            )
            return {"type": "text", "text": err_msg}

        err_msg = (
            "ระบบประมวลผลสำเร็จแต่ไม่มีข้อมูลที่ตรงกับคำถามครับ"
            if lang == "th"
            else "Processing successful, but no matching data was found."
        )
        return {"type": "text", "text": err_msg}
