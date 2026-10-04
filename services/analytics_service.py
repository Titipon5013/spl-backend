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
    CameraSnapshotPayload,
    DeviceHeartbeatPayload
)
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
import os


class AnalyticsService:
    MAX_QUERY_ROWS = int(os.getenv("ANALYTICS_MAX_QUERY_ROWS", "50000"))

    def __init__(self, db: Session):
        self.db = db

    CAMERA_HEALTH_DEVICES = (
        ("camera_1", "CAMT_01", "camera_1_status"),
        ("camera_2", "CAMT_02", "camera_2_status"),
        ("camera_3", "CAMT_03", "camera_3_status"),
        ("camera_4", "CAMT_04", "camera_4_status"),
    )

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
        ).limit(self.MAX_QUERY_ROWS).all()

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
        ).limit(self.MAX_QUERY_ROWS).all()

        utilization = 0.0
        peak_occupancy = 0
        if snapshots:
            utilization = sum(s.occupacy_rate for s in snapshots) / len(snapshots)
            peak_occupancy = max(s.occupied_spaces for s in snapshots)

        vehicle_count = self._vehicle_count_for_lot(lot_id, start_date, end_date)

        return {
            "lot_id": lot_id,
            "utilization_percentage": round(utilization, 2),
            "peak_occupancy": peak_occupancy,
            "vehicle_count": vehicle_count,
            "avg_dwell_time_minutes": round(self._calculate_avg_dwell_time(lot_id, start_date, end_date), 2),
        }

    def _vehicle_count_for_lot(
        self, lot_id: str, start_date: datetime, end_date: datetime
    ) -> int:
        """นับรถเข้าเฉพาะลานนี้ ถ้ามีข้อมูลที่ระบุ lot แล้ว (ถอยกลับไปนับรวมทั้งระบบถ้ายังไม่มี)"""
        window = (
            EntryRecord.timestamp >= start_date,
            EntryRecord.timestamp <= end_date,
        )
        has_tagged_lot = (
            self.db.query(EntryRecord)
            .filter(*window, EntryRecord.lot_id.isnot(None))
            .first()
            is not None
        )
        if not has_tagged_lot:
            return self.db.query(EntryRecord).filter(*window).count()

        return (
            self.db.query(EntryRecord)
            .filter(*window, EntryRecord.lot_id == lot_id)
            .count()
        )

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

    def get_live_occupancy(self, lot_id: str) -> Optional[dict]:
        """สถานะลานจอดล่าสุด (URS-08). คืนค่า None ถ้ายังไม่มีข้อมูลเข้ามาเลย"""
        model = ParkingSnapshot if lot_id == "CAMT_01" else ParkingSnapshot2
        latest = (
            self.db.query(model)
            .filter(model.lot_id == lot_id)
            .order_by(model.timestamp.desc())
            .first()
        )
        if not latest:
            return None

        return {
            "lot_id": lot_id,
            "total_spaces": latest.total_spaces,
            "available_spaces": latest.available_spaces,
            "occupied_spaces": latest.occupied_spaces,
            "occupancy_rate": round(latest.occupacy_rate, 2),
            "confidence": latest.confidence,
            "timestamp": latest.timestamp.isoformat(),
            "data_age_seconds": int((datetime.now() - latest.timestamp).total_seconds()),
        }

    def _latest_event_per_spot(self, lot_id: str) -> list[ParkingEventLog]:
        """เหตุการณ์ล่าสุดของแต่ละช่องจอดในลานที่ระบุ

        ใช้ max(id) ต่อ spot_id เพราะ id เพิ่มขึ้นตามลำดับการบันทึกเสมอ
        จึงไม่กำกวมเหมือนใช้ max(timestamp) ที่อาจซ้ำกันได้
        """
        latest_ids = (
            self.db.query(func.max(ParkingEventLog.id))
            .filter(ParkingEventLog.lot_id == lot_id)
            .group_by(ParkingEventLog.spot_id)
            .scalar_subquery()
        )
        return (
            self.db.query(ParkingEventLog)
            .filter(ParkingEventLog.id.in_(latest_ids))
            .order_by(ParkingEventLog.spot_id)
            .all()
        )

    def check_slot_status(self, lot_id: str, spot_id: str) -> Optional[dict]:
        """สถานะปัจจุบันของช่องจอดที่ระบุ (URS-09). คืนค่า None ถ้าไม่รู้จักช่องนี้"""
        latest = (
            self.db.query(ParkingEventLog)
            .filter(
                ParkingEventLog.lot_id == lot_id,
                ParkingEventLog.spot_id == spot_id,
            )
            .order_by(ParkingEventLog.id.desc())
            .first()
        )
        if not latest:
            return None

        return {
            "lot_id": lot_id,
            "spot_id": spot_id,
            "state": "occupied" if latest.is_occupied else "free",
            "since": latest.timestamp.isoformat(),
            "duration_minutes": round(
                (datetime.now() - latest.timestamp).total_seconds() / 60, 1
            ),
        }

    def find_available_slots(self, lot_id: str) -> dict:
        """ช่องจอดที่ว่างอยู่ตอนนี้ (URS-10)."""
        latest_events = self._latest_event_per_spot(lot_id)

        available = [event.spot_id for event in latest_events if not event.is_occupied]
        occupied = [event.spot_id for event in latest_events if event.is_occupied]

        return {
            "lot_id": lot_id,
            "available_count": len(available),
            "occupied_count": len(occupied),
            "known_spots": len(latest_events),
            "available_spots": available,
        }

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
            .limit(self.MAX_QUERY_ROWS)
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

    def process_orange_pi_snapshot(self, payload: CameraSnapshotPayload) -> str:
        current_time = datetime.now()

        model = ParkingSnapshot if payload.lot_id == "CAMT_01" else ParkingSnapshot2
        new_snapshot = model(
            lot_id=payload.lot_id,
            total_spaces=payload.total_spaces,
            available_spaces=payload.available_spaces,
            occupied_spaces=payload.occupied_spaces,
            occupacy_rate=payload.occupacy_rate,
            confidence=payload.confidence,
            processing_time_seconds=payload.processing_time_seconds,
            timestamp=current_time
        )
        self.db.add(new_snapshot)

        if payload.lot_id == "CAMT_01":
            zone_a = [f"A{i}" for i in range(1, 14)]
            zone_c = [f"C{i}" for i in range(1, 16)]
            zone_b = [f"B{i:02d}" for i in range(1, 7)]
            actual_spots = zone_a + zone_c + zone_b
        else:
            actual_spots = [f"Spot_{str(i).zfill(2)}" for i in range(1, payload.total_spaces + 1)]

        new_events = []
        for index, spot in enumerate(actual_spots):
            # ถ้ารถยังไม่เกินจำนวน occupied_spaces ให้ใส่เป็น True (มีรถ) นอกนั้นใส่ False (ว่าง)
            is_occupied = True if index < payload.occupied_spaces else False
            new_events.append(
                ParkingEventLog(
                    lot_id=payload.lot_id,
                    spot_id=spot,
                    is_occupied=is_occupied,
                    timestamp=current_time
                )
            )
        self.db.bulk_save_objects(new_events)

        # 1. อัปเดตสถานะบอร์ด ORANGE_PI_MAIN (ของเดิม)
        device = self.db.query(DeviceHealth).filter(DeviceHealth.device_id == "ORANGE_PI_MAIN").first()
        if not device:
            device = DeviceHealth(device_id="ORANGE_PI_MAIN", device_type="board", status="online",
                                  last_seen=current_time)
            self.db.add(device)
        else:
            device.status = "online"
            device.last_seen = current_time

        # 2. 🟢 อัปเดตสถานะกล้อง (ส่วนที่เพิ่มเข้ามาใหม่)
        camera = self.db.query(DeviceHealth).filter(DeviceHealth.device_id == payload.lot_id).first()
        if not camera:
            camera = DeviceHealth(device_id=payload.lot_id, device_type="camera", status="online",
                                  last_seen=current_time)
            self.db.add(camera)
        else:
            camera.status = "online"
            camera.last_seen = current_time

        self.db.commit()

        return f"Processed snapshot for {payload.lot_id}, distributed to {len(actual_spots)} spots, and updated board & camera health."

    def update_hardware_heartbeat(self, payload: DeviceHeartbeatPayload) -> bool:
        try:
            self._upsert_device_health("board", "ORANGE_PI_MAIN", payload.board_status)
            for device_type, device_id, status_attr in self.CAMERA_HEALTH_DEVICES:
                self._upsert_device_health(
                    device_type,
                    device_id,
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
            device.last_seen = datetime.now()
        else:
            new_device = DeviceHealth(device_id=device_id, device_type=device_type, status=status,
                                      last_seen=datetime.now())
            self.db.add(new_device)

    def get_system_health_status(self, lot_id: str) -> SystemHealthResponse:
        # 1. ฟังก์ชันเดิม: ดึงสถานะจาก DB (ใช้สำหรับ Orange Pi Board)
        def get_device_status_from_db(dev_id: str) -> DeviceStatus:
            dev = self.db.query(DeviceHealth).filter(DeviceHealth.device_id == dev_id).first()
            if not dev:
                return DeviceStatus(status="offline", last_seen=None)
            if dev.last_seen and (datetime.now() - dev.last_seen).total_seconds() > 300:
                return DeviceStatus(status="offline", last_seen=dev.last_seen)
            return DeviceStatus(status=dev.status, last_seen=dev.last_seen)

        # 2. ฟังก์ชันใหม่: เช็คจากไฟล์สตรีม m3u8 (ใช้สำหรับกล้องทั้ง 4 ตัว)
        def get_camera_status_from_stream(cam_name: str, stream_folder: str) -> DeviceStatus:
            # หมายเหตุ: ปรับ "/app/streams/" ให้ตรงกับ Path จริงที่เก็บไฟล์วิดีโอใน Docker ของคุณ
            file_path = f"/app/streams/{stream_folder}/index.m3u8"
            try:
                if os.path.exists(file_path):
                    mtime = os.path.getmtime(file_path)
                    # ถ้าไฟล์เพิ่งมีการเขียนใหม่ภายใน 3 นาที (180 วินาที) ถือว่ากล้องออนไลน์ 100%
                    if (datetime.now().timestamp() - mtime) < 180:
                        return DeviceStatus(status="online", last_seen=datetime.fromtimestamp(mtime))
            except Exception as e:
                print(f"Stream check error for {cam_name}: {e}")

            # ถ้าไฟล์ไม่มีหรือสตรีมค้าง ให้ถอยกลับไปเช็คจาก DB แทน
            return get_device_status_from_db(cam_name)

        # ตรวจสอบบอร์ดจาก DB
        board_stat = get_device_status_from_db("ORANGE_PI_MAIN")

        # ตรวจสอบกล้องจากการมีอยู่ของไฟล์สตรีม
        cam1_stat = get_camera_status_from_stream("CAMT_01", "parking")
        cam2_stat = get_camera_status_from_stream("CAMT_02", "parking2")
        cam3_stat = get_camera_status_from_stream("CAMT_03", "license")
        cam4_stat = get_camera_status_from_stream("CAMT_04", "license1")

        camera_stats = (cam1_stat, cam2_stat, cam3_stat, cam4_stat)

        if board_stat.status == "offline":
            sys_status = "Critical"
        elif any(camera.status == "offline" for camera in camera_stats):
            sys_status = "Degraded"
        else:
            sys_status = "Healthy"

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
        if device.status not in ["online", "healthy"] or not device.last_seen:
            return 0.0
        age_seconds = (datetime.now() - device.last_seen).total_seconds()
        if age_seconds > 300:
            return 0.0
        return max(0.0, 100.0 - (age_seconds / 300) * 20)
