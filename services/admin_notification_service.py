"""Feature 4 admin LINE push notifications for new system anomalies (UC-10)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Callable, Optional

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import AdminAlertDelivery, AdminAlertSubscription, DeviceHealth, SystemAnomaly
from services.admin_chatbot_service import DEFAULT_ALERT_TYPES


PushFn = Callable[[str, str], None]

# While campus services are paused / noisy, only push hardware-style alerts by default.
# Override with ADMIN_PUSH_ALERT_TYPES="device_offline,pipeline_inactive" if needed.
_LEGACY_ALL_TYPES = "stuck_slot,pipeline_inactive,device_offline"

DEVICE_TYPE_LABELS_TH = {
    "board": "บอร์ดควบคุม",
    "camera_1": "กล้อง 1",
    "camera_2": "กล้อง 2",
    "camera_3": "กล้อง 3",
    "camera_4": "กล้อง 4",
}


def _default_push(line_user_id: str, text: str) -> None:
    token = os.getenv("ADMIN_LINE_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("ADMIN_LINE_ACCESS_TOKEN is not configured")

    configuration = Configuration(access_token=token)
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(
                to=line_user_id,
                messages=[TextMessage(text=text)],
            )
        )


def pushable_alert_types() -> set[str]:
    """Global allow-list for LINE pushes (intersected with each subscription)."""
    raw = os.getenv("ADMIN_PUSH_ALERT_TYPES", DEFAULT_ALERT_TYPES).strip()
    if not raw:
        raw = DEFAULT_ALERT_TYPES
    return {part.strip() for part in raw.split(",") if part.strip()}


def _parse_alert_types(raw: Optional[str]) -> set[str]:
    value = (raw or DEFAULT_ALERT_TYPES).strip()
    # Old links subscribed to every anomaly type; treat that as "use current defaults"
    # so stuck_slot spam stops without asking everyone to re-link.
    if not value or value == _LEGACY_ALL_TYPES:
        value = DEFAULT_ALERT_TYPES
    return {part.strip() for part in value.split(",") if part.strip()}


def _device_label(db: Session, device_id: Optional[str]) -> str:
    if not device_id:
        return "อุปกรณ์"
    row = (
        db.query(DeviceHealth)
        .filter(DeviceHealth.device_id == device_id)
        .first()
    )
    if row and row.device_type in DEVICE_TYPE_LABELS_TH:
        return f"{DEVICE_TYPE_LABELS_TH[row.device_type]} ({device_id})"
    return device_id


def _minutes_since(detected_at: Optional[datetime]) -> Optional[int]:
    if not detected_at:
        return None
    return max(0, int((datetime.utcnow() - detected_at).total_seconds() / 60))


def format_anomaly_alert(anomaly: SystemAnomaly, db: Optional[Session] = None) -> str:
    """Human LINE text — hardware-focused, not raw robot fields."""
    minutes = _minutes_since(anomaly.detected_at)

    if anomaly.anomaly_type == "device_offline":
        label = _device_label(db, anomaly.device_id) if db is not None else (
            anomaly.device_id or "อุปกรณ์"
        )
        ago = f" ประมาณ {minutes} นาทีแล้ว" if minutes is not None else ""
        return (
            f"⚠️ อุปกรณ์หลุด\n"
            f"{label} ไม่ส่งสัญญาณ{ago}\n"
            f"เช็คบอร์ด / กล้อง / ตัวกระจายสัญญาณในแดชบอร์ด System Health ได้เลยครับ"
        )

    if anomaly.anomaly_type == "pipeline_inactive":
        lot = anomaly.lot_id or "ลานจอด"
        ago = f" ประมาณ {minutes} นาทีแล้ว" if minutes is not None else ""
        return (
            f"⚠️ สัญญาณจากลานจอดเงียบ\n"
            f"{lot} ไม่มีข้อมูลเข้ามา{ago}\n"
            f"น่าจะเป็นกล้องหรือเส้นทางส่งข้อมูลหลุด — ลองเทียบกับ System Health ครับ"
        )

    # stuck_slot and anything else (normally filtered out of pushes)
    spot = anomaly.spot_id or "?"
    lot = anomaly.lot_id or "?"
    return (
        f"ℹ️ ช่องจอดค้างสถานะ\n"
        f"ลาน {lot} ช่อง {spot} รายงานว่ามีรถจอดนานผิดปกติ\n"
        f"ถ้า feed ยังไม่เสถียร อาจเป็น false alarm ได้ครับ"
    )


class AdminNotificationService:
    def __init__(self, db: Session, push_fn: Optional[PushFn] = None):
        self.db = db
        self.push_fn = push_fn or _default_push

    def _already_delivered(self, anomaly_id: int, line_user_id: str) -> bool:
        return (
            self.db.query(AdminAlertDelivery)
            .filter(
                AdminAlertDelivery.anomaly_id == anomaly_id,
                AdminAlertDelivery.line_user_id == line_user_id,
            )
            .first()
            is not None
        )

    def _record_delivery(self, anomaly_id: int, line_user_id: str) -> bool:
        """Insert delivery row. Returns False if already delivered (unique conflict)."""
        if self._already_delivered(anomaly_id, line_user_id):
            return False
        self.db.add(
            AdminAlertDelivery(
                anomaly_id=anomaly_id,
                line_user_id=line_user_id,
                sent_at=datetime.utcnow(),
            )
        )
        try:
            self.db.commit()
            return True
        except IntegrityError:
            self.db.rollback()
            return False

    def dispatch_new_anomaly_alerts(self) -> dict:
        """Push undelivered open anomalies to unmuted linked admins (hardware-first)."""
        anomalies = (
            self.db.query(SystemAnomaly)
            .filter(SystemAnomaly.resolved_at.is_(None))
            .order_by(SystemAnomaly.detected_at.asc())
            .all()
        )
        subscriptions = self.db.query(AdminAlertSubscription).all()
        global_allow = pushable_alert_types()

        pushed = 0
        skipped_muted = 0
        skipped_type = 0
        skipped_dup = 0
        failures = 0

        for anomaly in anomalies:
            for sub in subscriptions:
                if sub.muted:
                    skipped_muted += 1
                    continue

                allowed = _parse_alert_types(sub.alert_types) & global_allow
                if anomaly.anomaly_type not in allowed:
                    skipped_type += 1
                    continue

                if not self._record_delivery(anomaly.id, sub.line_user_id):
                    skipped_dup += 1
                    continue

                try:
                    self.push_fn(
                        sub.line_user_id,
                        format_anomaly_alert(anomaly, self.db),
                    )
                    pushed += 1
                except Exception as exc:
                    failures += 1
                    print(
                        f"[admin-notify] push failed for {sub.line_user_id} "
                        f"anomaly={anomaly.id}: {exc}"
                    )

        return {
            "open_anomalies": len(anomalies),
            "subscriptions": len(subscriptions),
            "pushed": pushed,
            "skipped_muted": skipped_muted,
            "skipped_type": skipped_type,
            "skipped_dup": skipped_dup,
            "failures": failures,
        }
