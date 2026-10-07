import json
from zoneinfo import ZoneInfo
from schemas.parking import LicensePlatePayload
from schemas.analytics import CameraSnapshotPayload  # 🟢 นำเข้า Schema ของ Analytics
from schemas.gate import GateEventPayload
from db.models import EntryRecord, GateEvent
from db.session import get_db
from datetime import datetime
from services.analytics_service import AnalyticsService  # 🟢 นำเข้า Service ที่เราเขียนไว้
from sqlalchemy.exc import IntegrityError


def on_connect(client, userdata, flags, rc, properties):
    print(f"on_connect: client_id={client._client_id.decode()}, rc={rc}")
    if rc == 0:
        print("MQTT connected successfully.")
        client.subscribe("test/parking", qos=1, options={"no_local": True})
        client.subscribe("test/parking2", qos=1, options={"no_local": True})
        client.subscribe("test/license", qos=1, options={"no_local": True})
        client.subscribe("test/gate", qos=1, options={"no_local": True})
    else:
        print(f"MQTT connection failed with code {rc}")


def on_message(client, userdata, msg):
    if msg.retain:
        print(f"Ignoring retained message: topic={msg.topic}")
        return

    db_gen = get_db()
    db = next(db_gen)

    try:
        topic = msg.topic
        payload = msg.payload.decode()
        print(f"Message received: topic={topic}, payload={payload}")

        data = json.loads(payload)

        if topic in ["test/parking", "test/parking2"]:
            # 1. กำหนด lot_id ตาม Topic
            lot_id = "CAMT_01" if topic == "test/parking" else "CAMT_02"

            # 2. ปั้น Payload ให้ตรงกับที่ AnalyticsService ต้องการ
            sync_payload = CameraSnapshotPayload(
                lot_id=lot_id,
                total_spaces=data.get("total_spaces", 34),
                available_spaces=data.get("available_spaces", 0),
                occupied_spaces=data.get("occupied_spaces", 0),
                occupacy_rate=data.get("occupancy_rate", 0.0),
                confidence=data.get("confidence", 0.0),
                processing_time_seconds=data.get("processing_time_seconds", 0.0)
            )

            # 3. 🟢 เรียกใช้ AnalyticsService ให้จัดการทุกอย่างแทน!
            service = AnalyticsService(db)
            result = service.process_orange_pi_snapshot(sync_payload)

            print(f"Successfully synced via AnalyticsService: {result}")

        elif topic == "test/license":
            validated = LicensePlatePayload(**data)
            entry_record = EntryRecord(
                plate_number=validated.plate_number,
                plate_image_url=validated.plate_image_url,
                timestamp=validated.timestamp if validated.timestamp else datetime.now(),
                lot_id=validated.lot_id,
            )
            db.add(entry_record)
            db.commit()
            print("Entry record saved to DB")

        elif topic == "test/gate":
            gate_event = GateEventPayload(**data)
            if gate_event.timestamp.tzinfo is None:
                gate_timestamp = gate_event.timestamp.replace(tzinfo=ZoneInfo("Asia/Bangkok"))
            else:
                gate_timestamp = gate_event.timestamp

            # QoS 1 permits redelivery. The database constraint is the final
            # guard against concurrent duplicate deliveries.
            if db.query(GateEvent.id).filter_by(event_id=gate_event.event_id).first():
                print(f"Duplicate gate event ignored: event_id={gate_event.event_id}")
                return

            db.add(GateEvent(
                event=gate_event.event,
                event_id=gate_event.event_id,
                gate_id=gate_event.gate_id,
                timestamp=gate_timestamp,
                vehicle_class=gate_event.vehicle_class,
                confidence=gate_event.confidence,
                camera=gate_event.camera,
                open_duration_seconds=gate_event.open_duration_seconds,
                open_count_today=gate_event.open_count_today,
                close_count_today=gate_event.close_count_today,
            ))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                print(f"Concurrent duplicate gate event ignored: event_id={gate_event.event_id}")
                return
            print(f"Gate event saved: gate_id={gate_event.gate_id}, event={gate_event.event}")

        else:
            print(f"Unhandled topic: {topic}")

    except Exception as err:
        print(f"Error processing message: {err}")
        db.rollback()
    finally:
        db.close()

# Sample Payload
# {
#   "lot_id": "CAMT_01",
#   "available_spots": 5
# }
# Full Payload (Updated for Heatmap Support)
# {
#   "lot_id": "CAMT_01",
#   "available_spaces": 12,
#   "total_spaces": 30,
#   "occupied_spaces": 18,
#   "occupancy_rate": 0.6,
#   "confidence": 0.95,
#   "processing_time_seconds": 0.12,
#   "timestamp": "2025-06-27T14:30:00Z",
#   "spot_details": [
#       {"spot_id": "A1", "is_occupied": true},
#       {"spot_id": "A2", "is_occupied": false}
#   ]
# }

# {
#     "plate_number": "WE3342",
#     "plate_image_url": "abcd"
# }
