import json
from schemas.parking import ParkingPayload, LicensePlatePayload
from db.models import ParkingSnapshot, EntryRecord, ParkingSnapshot2, ParkingEventLog
from db.session import get_db
from datetime import datetime


def on_connect(client, userdata, flags, rc, properties):
    print(f"on_connect: client_id={client._client_id.decode()}, rc={rc}")
    if rc == 0:
        print("MQTT connected successfully.")
        client.subscribe("test/parking", qos=1, options={"no_local": True})
        client.subscribe("test/parking2", qos=1, options={"no_local": True})
        client.subscribe("test/license", qos=1, options={"no_local": True})
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

        if topic == "test/parking" or topic == "test/parking2":
            validated = ParkingPayload(**data)

            if topic == "test/parking":
                snapshot = ParkingSnapshot(
                    lot_id=validated.lot_id,
                    timestamp=validated.timestamp if validated.timestamp else datetime.utcnow(),
                    available_spaces=validated.available_spaces,
                    total_spaces=validated.total_spaces,
                    occupied_spaces=validated.occupied_spaces,
                    occupacy_rate=validated.occupancy_rate,
                    confidence=validated.confidence,
                    processing_time_seconds=validated.processing_time_seconds
                )
            elif topic == "test/parking2":
                snapshot = ParkingSnapshot2(
                    lot_id=validated.lot_id,
                    timestamp=validated.timestamp if validated.timestamp else datetime.utcnow(),
                    available_spaces=validated.available_spaces,
                    total_spaces=validated.total_spaces,
                    occupied_spaces=validated.occupied_spaces,
                    occupacy_rate=validated.occupancy_rate,
                    confidence=validated.confidence,
                    processing_time_seconds=validated.processing_time_seconds
                )

            db.add(snapshot)

            if hasattr(validated, 'spot_details') and validated.spot_details:
                for spot in validated.spot_details:

                    last_log = db.query(ParkingEventLog).filter(
                        ParkingEventLog.lot_id == validated.lot_id,
                        ParkingEventLog.spot_id == spot.spot_id
                    ).order_by(ParkingEventLog.timestamp.desc()).first()

                    if not last_log or last_log.is_occupied != spot.is_occupied:
                        event_log = ParkingEventLog(
                            lot_id=validated.lot_id,
                            spot_id=spot.spot_id,
                            is_occupied=spot.is_occupied,
                            timestamp=validated.timestamp if validated.timestamp else datetime.utcnow()
                        )
                        db.add(event_log)

            db.commit()
            print(f"Parking snapshot and event logs saved to DB for topic: {topic}")

        elif topic == "test/license":
            validated = LicensePlatePayload(**data)
            entry_record = EntryRecord(
                plate_number=validated.plate_number,
                plate_image_url=validated.plate_image_url,
                timestamp=validated.timestamp if validated.timestamp else datetime.utcnow()
            )
            db.add(entry_record)
            db.commit()
            print("Entry record saved to DB")

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