from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from db.models import ParkingEventLog, ParkingSnapshot, ParkingSnapshot2, DeviceHealth, EntryRecord
from schemas.analytics import (
    HeatmapSpotResponse,
    HeatmapResponse,
    TrendResponse,
    TrendDataPoint,
    SystemHealthResponse,
    DeviceStatus,
    CameraEventPayload,
    DeviceHeartbeatPayload
)
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    CAMERA_HEALTH_DEVICES = (
        ("camera_1", "cam1", "camera_1_status"),
        ("camera_2", "cam2", "camera_2_status"),
        ("camera_3", "cam3", "camera_3_status"),
        ("camera_4", "cam4", "camera_4_status"),
    )

    # ========================================================
    # [1] Analytics Serving (ดึงข้อมูลไปโชว์หน้า Dashboard)
    # ========================================================
    def get_heatmap_data(self, lot_id: str, start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> HeatmapResponse:

        query = self.db.query(
            ParkingEventLog.spot_id,
            func.count(ParkingEventLog.id).label('total'),
            func.sum(cast(ParkingEventLog.is_occupied, Integer)).label('occupied')
        ).filter(ParkingEventLog.lot_id == lot_id)

        if start_date:
            query = query.filter(ParkingEventLog.timestamp >= start_date)
        if end_date:
            query = query.filter(ParkingEventLog.timestamp <= end_date)

        results = query.group_by(ParkingEventLog.spot_id).all()

        spot_responses = []
        for row in results:
            spot_id = row.spot_id
            total = row.total or 0
            occupied = row.occupied or 0

            percentage = (occupied / total * 100) if total > 0 else 0.0

            spot_responses.append(HeatmapSpotResponse(
                spot_id=spot_id,
                total_events=total,
                occupied_events=occupied,
                occupancy_percentage=round(percentage, 2)
            ))

        return HeatmapResponse(lot_id=lot_id, spots=spot_responses)

    def get_occupancy_trends(self, lot_id: str, start_date: datetime, end_date: datetime) -> TrendResponse:
        model = ParkingSnapshot if lot_id == "CAMT_01" else ParkingSnapshot2

        query = self.db.query(model).filter(
            model.lot_id == lot_id,
            model.timestamp >= start_date,
            model.timestamp <= end_date
        ).all()

        hourly_data = defaultdict(list)
        for snap in query:
            hour_str = snap.timestamp.strftime("%Y-%m-%d %H:00")
            hourly_data[hour_str].append(snap.occupied_spaces)

        trends = []
        max_avg = -1
        peak_hour = None

        for hour in sorted(hourly_data.keys()):
            spaces = hourly_data[hour]
            avg_space = sum(spaces) / len(spaces)
            trends.append(TrendDataPoint(time_label=hour, average_occupancy=round(avg_space, 2)))

            if avg_space > max_avg:
                max_avg = avg_space
                peak_hour = hour

        return TrendResponse(lot_id=lot_id, peak_hour=peak_hour, trends=trends)

    def get_kpis(self, lot_id: str, start_date: datetime, end_date: datetime) -> dict:
        model = ParkingSnapshot if lot_id == "CAMT_01" else ParkingSnapshot2
        snapshots = self.db.query(model).filter(
            model.lot_id == lot_id,
            model.timestamp >= start_date,
            model.timestamp <= end_date,
        ).all()

        utilization = 0.0
        peak_occupancy = 0
        if snapshots:
            utilization = sum(s.occupacy_rate for s in snapshots) / len(snapshots)
            peak_occupancy = max(s.occupied_spaces for s in snapshots)

        vehicle_count = self.db.query(EntryRecord).filter(
            EntryRecord.timestamp >= start_date,
            EntryRecord.timestamp <= end_date,
        ).count()

        return {
            "lot_id": lot_id,
            "utilization_percentage": round(utilization, 2),
            "peak_occupancy": peak_occupancy,
            "vehicle_count": vehicle_count,
            "avg_dwell_time_minutes": round(self._calculate_avg_dwell_time(lot_id, start_date, end_date), 2),
        }

    def get_slot_event_history(
        self,
        lot_id: str,
        spot_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        query = self.db.query(ParkingEventLog).filter(
            ParkingEventLog.lot_id == lot_id,
            ParkingEventLog.spot_id == spot_id,
        )
        if start_date:
            query = query.filter(ParkingEventLog.timestamp >= start_date)
        if end_date:
            query = query.filter(ParkingEventLog.timestamp <= end_date)

        events = query.order_by(ParkingEventLog.timestamp.desc()).limit(100).all()
        return [
            {
                "event_id": event.id,
                "spot_id": event.spot_id,
                "state": "occupied" if event.is_occupied else "free",
                "timestamp": event.timestamp.isoformat(),
            }
            for event in events
        ]

    def _calculate_avg_dwell_time(
        self, lot_id: str, start_date: datetime, end_date: datetime
    ) -> float:
        events = (
            self.db.query(ParkingEventLog)
            .filter(
                ParkingEventLog.lot_id == lot_id,
                ParkingEventLog.timestamp >= start_date,
                ParkingEventLog.timestamp <= end_date,
            )
            .order_by(ParkingEventLog.spot_id, ParkingEventLog.timestamp)
            .all()
        )

        dwell_minutes: list[float] = []
        occupied_at: dict[str, datetime] = {}

        for event in events:
            if event.is_occupied:
                occupied_at[event.spot_id] = event.timestamp
            elif event.spot_id in occupied_at:
                delta = (event.timestamp - occupied_at[event.spot_id]).total_seconds() / 60
                if delta > 0:
                    dwell_minutes.append(delta)
                del occupied_at[event.spot_id]

        return sum(dwell_minutes) / len(dwell_minutes) if dwell_minutes else 0.0

    # ========================================================
    # [2] Hardware Ingestion (รับข้อมูลจาก Orange Pi)
    # ========================================================
    def process_camera_events(self, payload: CameraEventPayload) -> str:
        # 1. วนลูปบันทึกประวัติ (Event Log) ทีละช่อง
        for event in payload.events:
            new_log = ParkingEventLog(
                lot_id=payload.lot_id,
                spot_id=event.spot_id,
                is_occupied=(event.status.lower() == 'occupied'),
                timestamp=datetime.utcnow()
            )
            self.db.add(new_log)

        # 2. อัปเดตตาราง Snapshot ปัจจุบัน (เพื่อให้ Chatbot มีข้อมูลตอบ)
        model = ParkingSnapshot if payload.lot_id == "CAMT_01" else ParkingSnapshot2
        occupancy_rate = (payload.occupied_spaces / payload.total_spaces * 100) if payload.total_spaces > 0 else 0.0

        new_snapshot = model(
            lot_id=payload.lot_id,
            total_spaces=payload.total_spaces,
            available_spaces=payload.available_spaces,
            occupied_spaces=payload.occupied_spaces,
            occupacy_rate=occupancy_rate,
            confidence=payload.confidence,
            processing_time_seconds=payload.processing_time_seconds,
            timestamp=datetime.utcnow()
        )
        self.db.add(new_snapshot)

        # บันทึกทั้ง 2 ตารางลง Database ใน Transaction เดียวเลย
        self.db.commit()

        return f"Processed {len(payload.events)} events and updated snapshot for {payload.lot_id}"

    # ========================================================
    # [3] System Health Monitoring (เช็คสถานะอุปกรณ์)
    # ========================================================
    def update_hardware_heartbeat(self, payload: DeviceHeartbeatPayload) -> bool:
        try:
            self._upsert_device_health("board", payload.board_id, payload.board_status)
            for device_type, device_suffix, status_attr in self.CAMERA_HEALTH_DEVICES:
                self._upsert_device_health(
                    device_type,
                    f"{payload.board_id}_{device_suffix}",
                    getattr(payload, status_attr),
                )
            self.db.commit()
            return True
        except Exception as e:
            print(f"Failed to save heartbeat: {e}")
            self.db.rollback()
            return False

    def _upsert_device_health(self, device_type: str, device_id: str, status: str):
        device = self.db.query(DeviceHealth).filter(DeviceHealth.device_id == device_id).first()
        if device:
            device.status = status
            device.last_seen = datetime.utcnow()
        else:
            new_device = DeviceHealth(device_id=device_id, device_type=device_type, status=status,
                                      last_seen=datetime.utcnow())
            self.db.add(new_device)

    def get_system_health_status(self, lot_id: str) -> SystemHealthResponse:
        def get_device_status(dev_type: str) -> DeviceStatus:
            dev = self.db.query(DeviceHealth).filter(DeviceHealth.device_type == dev_type).first()
            if not dev:
                return DeviceStatus(status="offline", last_seen=None)

            # 💡 ตรรกะสำคัญ: ถ้าข้อมูลอัปเดตล่าสุดนานเกิน 5 นาที (300 วินาที) ให้ถือว่า "Offline" อัตโนมัติ
            if dev.last_seen and (datetime.utcnow() - dev.last_seen).total_seconds() > 300:
                return DeviceStatus(status="offline", last_seen=dev.last_seen)

            return DeviceStatus(status=dev.status, last_seen=dev.last_seen)

        board_stat = get_device_status("board")
        cam1_stat = get_device_status("camera_1")
        cam2_stat = get_device_status("camera_2")
        cam3_stat = get_device_status("camera_3")
        cam4_stat = get_device_status("camera_4")
        camera_stats = (cam1_stat, cam2_stat, cam3_stat, cam4_stat)

        # ประเมินสถานะภาพรวมของระบบ (System Status)
        if board_stat.status == "offline":
            sys_status = "Critical"  # บอร์ดดับ = พังทั้งระบบ
        elif any(camera.status == "offline" for camera in camera_stats):
            sys_status = "Degraded"  # บอร์ดติด แต่กล้องตัวใดตัวหนึ่งดับ
        else:
            sys_status = "Healthy"  # ปกติดีทุกตัว

        uptime = round(
            (
                self._device_uptime_score(board_stat)
                + sum(self._device_uptime_score(camera) for camera in camera_stats)
            )
            / 5,
            2,
        )

        return SystemHealthResponse(
            system_status=sys_status,
            uptime_percentage=uptime,
            board=board_stat,
            camera_1=cam1_stat,
            camera_2=cam2_stat,
            camera_3=cam3_stat,
            camera_4=cam4_stat
        )

    def _device_uptime_score(self, device: DeviceStatus) -> float:
        if device.status != "online" or not device.last_seen:
            return 0.0
        age_seconds = (datetime.utcnow() - device.last_seen).total_seconds()
        if age_seconds > 300:
            return 0.0
        return max(0.0, 100.0 - (age_seconds / 300) * 20)
