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

from db.models import AdminAlertDelivery, AdminAlertSubscription, SystemAnomaly
from services.admin_chatbot_service import DEFAULT_ALERT_TYPES


PushFn = Callable[[str, str], None]


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


def _parse_alert_types(raw: Optional[str]) -> set[str]:
    value = (raw or DEFAULT_ALERT_TYPES).strip()
    if not value:
        value = DEFAULT_ALERT_TYPES
    return {part.strip() for part in value.split(",") if part.strip()}


def format_anomaly_alert(anomaly: SystemAnomaly) -> str:
    lot = anomaly.lot_id or "-"
    spot = anomaly.spot_id or "-"
    device = anomaly.device_id or "-"
    detected = (
        anomaly.detected_at.isoformat()
        if anomaly.detected_at
        else datetime.utcnow().isoformat()
    )
    return (
        f"🚨 ParkPilot alert ({anomaly.severity})\n"
        f"type: {anomaly.anomaly_type}\n"
        f"lot: {lot} | spot: {spot} | device: {device}\n"
        f"detected: {detected}\n"
        f"{anomaly.details}\n"
        f"(anomaly_id={anomaly.id})"
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
        """Push unread open anomalies to unmuted linked admins (once each)."""
        anomalies = (
            self.db.query(SystemAnomaly)
            .filter(SystemAnomaly.resolved_at.is_(None))
            .order_by(SystemAnomaly.detected_at.asc())
            .all()
        )
        subscriptions = self.db.query(AdminAlertSubscription).all()

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

                allowed = _parse_alert_types(sub.alert_types)
                if anomaly.anomaly_type not in allowed:
                    skipped_type += 1
                    continue

                if not self._record_delivery(anomaly.id, sub.line_user_id):
                    skipped_dup += 1
                    continue

                try:
                    self.push_fn(sub.line_user_id, format_anomaly_alert(anomaly))
                    pushed += 1
                except Exception as exc:
                    failures += 1
                    print(
                        f"[admin-notify] push failed for {sub.line_user_id} "
                        f"anomaly={anomaly.id}: {exc}"
                    )
                    # Keep the delivery row so we do not spam retries on a
                    # permanently broken LINE user; operators can clear the row.

        return {
            "open_anomalies": len(anomalies),
            "subscriptions": len(subscriptions),
            "pushed": pushed,
            "skipped_muted": skipped_muted,
            "skipped_type": skipped_type,
            "skipped_dup": skipped_dup,
            "failures": failures,
        }
