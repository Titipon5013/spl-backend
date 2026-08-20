import sys
import os
import random
from datetime import datetime, timedelta

# บังคับให้สคริปต์รู้จักโฟลเดอร์โปรเจกต์ปัจจุบัน
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.session import get_db
from db.models import ParkingSnapshot2, ParkingEventLog


def generate_mock_data():
    # ดึง Session ผ่าน get_db() แทน
    db = next(get_db())

    try:
        lot_id = "CAMT_02"
        total_spots = 34

        # รายชื่อช่องจอดตามพิกัดจริง (โซน A, B, C)
        actual_spots = [
            "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13",
            "B1", "B2", "B3", "B4", "B5", "B6",
            "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13", "C14", "C15"
        ]

        print("🚀 เริ่มสร้างข้อมูลจำลองย้อนหลัง 7 วัน...")

        now = datetime.utcnow()
        start_date = now - timedelta(days=7)

        snapshots_to_insert = []
        events_to_insert = []

        # วนลูป 7 วัน
        for day_offset in range(7):
            current_date = start_date + timedelta(days=day_offset)

            # วนลูปเวลา 07:00 ถึง 18:00
            for hour in range(7, 19):
                # สร้างข้อมูลทุกๆ 15 นาที
                for minute in (0, 15, 30, 45):
                    timestamp = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                    if 7 <= hour < 9:
                        occupied = random.randint(10, 25)
                    elif 9 <= hour < 15:
                        occupied = random.randint(30, 34)
                    elif 15 <= hour < 17:
                        occupied = random.randint(20, 30)
                    else:
                        occupied = random.randint(5, 15)

                    available = total_spots - occupied
                    occupancy_rate = (occupied / total_spots) * 100

                    snapshots_to_insert.append(
                        ParkingSnapshot2(
                            lot_id=lot_id,
                            timestamp=timestamp,
                            total_spaces=total_spots,
                            available_spaces=available,
                            occupied_spaces=occupied,
                            occupacy_rate=occupancy_rate,
                            confidence=round(random.uniform(0.92, 0.99), 2),
                            processing_time_seconds=round(random.uniform(0.05, 0.2), 3)
                        )
                    )

                    for index, spot in enumerate(actual_spots):
                        is_occupied = True if index < occupied else False
                        events_to_insert.append(
                            ParkingEventLog(
                                lot_id=lot_id,
                                spot_id=spot,
                                is_occupied=is_occupied,
                                timestamp=timestamp
                            )
                        )

        print(f"📦 กำลังบันทึก Snapshots: {len(snapshots_to_insert)} แถว...")
        db.bulk_save_objects(snapshots_to_insert)

        print(f"📦 กำลังบันทึก Event Logs: {len(events_to_insert)} แถว...")
        db.bulk_save_objects(events_to_insert)

        db.commit()
        print("✅ จำลองข้อมูลเสร็จสมบูรณ์! เปิดดู Dashboard ได้เลยครับ")

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    generate_mock_data()