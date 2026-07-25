import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from db.models import DeviceHealth, ParkingEventLog, SystemAnomaly
from services.analytics_service import AnalyticsService

# ค่าเริ่มต้นของตัวตรวจจับ ปรับได้ผ่าน environment variable
STUCK_SLOT_HOURS = int(os.getenv("ANOMALY_STUCK_SLOT_HOURS", "12"))
PIPELINE_INACTIVE_MINUTES = int(os.getenv("ANOMALY_PIPELINE_INACTIVE_MINUTES", "15"))
DEVICE_OFFLINE_SECONDS = int(os.getenv("ANOMALY_DEVICE_OFFLINE_SECONDS", "300"))

MONITORED_LOTS = ("CAMT_01", "CAMT_02")

STUCK_SLOT = "stuck_slot"
PIPELINE_INACTIVE = "pipeline_inactive"
DEVICE_OFFLINE = "device_offline"


class AnomalyService:
    """ตรวจจับและจัดการความผิดปกติของระบบ (URS-13, URS-14)

    ตัวตรวจจับทำงานแบบ idempotent คือ ความผิดปกติเดียวกันที่ยังไม่หาย
    จะไม่ถูกบันทึกซ้ำ และจะถูกปิด (resolved) อัตโนมัติเมื่อสถานการณ์กลับสู่ปกติ
    ทำให้ Feature 4 อ่านตารางนี้ไปแจ้งเตือนได้โดยไม่ส่งซ้ำ
    """

    def __init__(self, db: Session):
        self.db = db
        self.analytics_service = AnalyticsService(db)

    # ========================================================
    # [1] Detection (เรียกโดย scheduler)
    # ========================================================
    def detect_anomalies(self) -> dict:
        now = datetime.utcnow()
        active_keys: set[tuple] = set()
        opened = 0

        for finding in self._find_all(now):
            key = (
                finding["anomaly_type"],
                finding.get("lot_id"),
                finding.get("spot_id"),
                finding.get("device_id"),
            )
            active_keys.add(key)
            if self._open_anomaly(*key) is None:
                self.db.add(SystemAnomaly(detected_at=now, **finding))
                opened += 1

        resolved = self._resolve_absent(active_keys, now)
        self.db.commit()

        return {
            "detected_at": now.isoformat(),
            "new_anomalies": opened,
            "resolved_anomalies": resolved,
            "open_anomalies": self._open_query().count(),
        }

    def _find_all(self, now: datetime) -> list[dict]:
        findings: list[dict] = []
        for lot_id in MONITORED_LOTS:
            findings.extend(self._find_stuck_slots(lot_id, now))
            findings.extend(self._find_pipeline_inactivity(lot_id, now))
        findings.extend(self._find_offline_devices(now))
        return findings

    def _find_stuck_slots(self, lot_id: str, now: datetime) -> list[dict]:
        """ช่องจอดที่รายงานว่ามีรถจอดติดต่อกันนานผิดปกติ"""
        threshold = now - timedelta(hours=STUCK_SLOT_HOURS)
        findings = []

        for event in self.analytics_service._latest_event_per_spot(lot_id):
            if not event.is_occupied or event.timestamp > threshold:
                continue

            hours = (now - event.timestamp).total_seconds() / 3600
            findings.append({
                "anomaly_type": STUCK_SLOT,
                "severity": "warning",
                "lot_id": lot_id,
                "spot_id": event.spot_id,
                "device_id": None,
                "details": (
                    f"Slot {event.spot_id} has reported occupied for {hours:.1f} hours "
                    f"(threshold {STUCK_SLOT_HOURS}h). The vehicle may have left without "
                    f"being detected, or the slot may be mis-calibrated."
                ),
            })

        return findings

    def _find_pipeline_inactivity(self, lot_id: str, now: datetime) -> list[dict]:
        """ไม่มี event เข้ามาเลยในช่วงเวลาที่กำหนด แปลว่า pipeline อาจหยุดทำงาน"""
        threshold = now - timedelta(minutes=PIPELINE_INACTIVE_MINUTES)

        latest = (
            self.db.query(ParkingEventLog)
            .filter(ParkingEventLog.lot_id == lot_id)
            .order_by(ParkingEventLog.id.desc())
            .first()
        )

        # ยังไม่เคยมีข้อมูลเข้ามาเลย ถือว่ายังไม่ได้ติดตั้ง ไม่ใช่ความผิดปกติ
        if latest is None or latest.timestamp > threshold:
            return []

        minutes = (now - latest.timestamp).total_seconds() / 60
        return [{
            "anomaly_type": PIPELINE_INACTIVE,
            "severity": "critical",
            "lot_id": lot_id,
            "spot_id": None,
            "device_id": None,
            "details": (
                f"No parking events received for lot {lot_id} in {minutes:.0f} minutes "
                f"(threshold {PIPELINE_INACTIVE_MINUTES}m). The edge detection pipeline "
                f"may have stopped."
            ),
        }]

    def _find_offline_devices(self, now: datetime) -> list[dict]:
        """อุปกรณ์ที่ขาดการติดต่อ ใช้เกณฑ์เดียวกับหน้า System Health"""
        threshold = now - timedelta(seconds=DEVICE_OFFLINE_SECONDS)
        findings = []

        for device in self.db.query(DeviceHealth).all():
            is_stale = device.last_seen is None or device.last_seen < threshold
            if device.status == "online" and not is_stale:
                continue

            last_seen = device.last_seen.isoformat() if device.last_seen else "never"
            findings.append({
                "anomaly_type": DEVICE_OFFLINE,
                "severity": "critical" if device.device_type == "board" else "warning",
                "lot_id": None,
                "spot_id": None,
                "device_id": device.device_id,
                "details": (
                    f"Device {device.device_id} ({device.device_type}) is not reporting. "
                    f"Status: {device.status}, last seen: {last_seen}."
                ),
            })

        return findings

    # ========================================================
    # [2] Retrieval and review (เรียกโดย MCP tools)
    # ========================================================
    def get_anomalies(
        self,
        anomaly_type: Optional[str] = None,
        include_reviewed: bool = False,
        include_resolved: bool = False,
        limit: int = 50,
    ) -> list[dict]:
        query = self.db.query(SystemAnomaly)

        if not include_resolved:
            query = query.filter(SystemAnomaly.resolved_at.is_(None))
        if not include_reviewed:
            query = query.filter(SystemAnomaly.reviewed_at.is_(None))
        if anomaly_type:
            query = query.filter(SystemAnomaly.anomaly_type == anomaly_type)

        anomalies = (
            query.order_by(SystemAnomaly.detected_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return [self._serialize(anomaly) for anomaly in anomalies]

    def mark_anomaly_reviewed(self, anomaly_id: int, reviewed_by: str) -> Optional[dict]:
        """คืนค่า None ถ้าไม่พบ anomaly id นี้"""
        anomaly = (
            self.db.query(SystemAnomaly)
            .filter(SystemAnomaly.id == anomaly_id)
            .first()
        )
        if anomaly is None:
            return None

        anomaly.reviewed_by = reviewed_by
        anomaly.reviewed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(anomaly)
        return self._serialize(anomaly)

    # ========================================================
    # Internal helpers
    # ========================================================
    def _open_query(self):
        return self.db.query(SystemAnomaly).filter(SystemAnomaly.resolved_at.is_(None))

    def _open_anomaly(
        self,
        anomaly_type: str,
        lot_id: Optional[str],
        spot_id: Optional[str],
        device_id: Optional[str],
    ) -> Optional[SystemAnomaly]:
        query = self._open_query().filter(SystemAnomaly.anomaly_type == anomaly_type)
        for column, value in (
            (SystemAnomaly.lot_id, lot_id),
            (SystemAnomaly.spot_id, spot_id),
            (SystemAnomaly.device_id, device_id),
        ):
            query = query.filter(column.is_(None) if value is None else column == value)
        return query.first()

    def _resolve_absent(self, active_keys: set[tuple], now: datetime) -> int:
        """ปิดความผิดปกติที่ไม่พบแล้วในรอบตรวจนี้"""
        resolved = 0
        for anomaly in self._open_query().all():
            key = (
                anomaly.anomaly_type,
                anomaly.lot_id,
                anomaly.spot_id,
                anomaly.device_id,
            )
            if key not in active_keys:
                anomaly.resolved_at = now
                resolved += 1
        return resolved

    def _serialize(self, anomaly: SystemAnomaly) -> dict:
        return {
            "anomaly_id": anomaly.id,
            "anomaly_type": anomaly.anomaly_type,
            "severity": anomaly.severity,
            "lot_id": anomaly.lot_id,
            "spot_id": anomaly.spot_id,
            "device_id": anomaly.device_id,
            "details": anomaly.details,
            "detected_at": anomaly.detected_at.isoformat(),
            "resolved_at": anomaly.resolved_at.isoformat() if anomaly.resolved_at else None,
            "reviewed_by": anomaly.reviewed_by,
            "reviewed_at": anomaly.reviewed_at.isoformat() if anomaly.reviewed_at else None,
        }
