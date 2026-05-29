from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from db.models import ParkingEventLog, ParkingSnapshot, ParkingSnapshot2, \
    DeviceHealth  # ⚠️ ดูหมายเหตุด้านล่างเรื่อง DeviceHealth
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
            # ฟังก์ชันช่วยบันทึก/อัปเดตข้อมูลอุปกรณ์ (Upsert)
            self._upsert_device_health("board", payload.board_id, payload.board_status)
            self._upsert_device_health("camera_1", f"{payload.board_id}_cam1", payload.camera_1_status)
            self._upsert_device_health("camera_2", f"{payload.board_id}_cam2", payload.camera_2_status)
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

        # ประเมินสถานะภาพรวมของระบบ (System Status)
        if board_stat.status == "offline":
            sys_status = "Critical"  # บอร์ดดับ = พังทั้งระบบ
        elif cam1_stat.status == "offline" or cam2_stat.status == "offline":
            sys_status = "Degraded"  # บอร์ดติด แต่กล้องตัวใดตัวหนึ่งดับ
        else:
            sys_status = "Healthy"  # ปกติดีทุกตัว

        return SystemHealthResponse(
            system_status=sys_status,
            uptime_percentage=99.8,  # สามารถเขียนสูตรคำนวณ Uptime จริงทีหลังได้
            board=board_stat,
            camera_1=cam1_stat,
            camera_2=cam2_stat
        )