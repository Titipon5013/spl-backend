import json
from schemas.parking import ParkingPayload, LicensePlatePayload
from db.models import ParkingSnapshot, EntryRecord, ParkingSnapshot2
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

        if topic == "test/parking":
            validated = ParkingPayload(**data)
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
            db.add(snapshot)
            db.commit()
            print("Parking snapshot 1 saved to DB")

        elif topic == "test/parking2":
            validated = ParkingPayload(**data)
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
            db.commit()
            print("Parking snapshot 2 saved to DB")

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
# Full Payload
# {
#   "lot_id": "CAMT_01",
#   "available_spots": 12,
#   "total_spots": 30,
#   "timestamp": "2025-06-27T14:30:00Z"
# }

# {
#     "plate_number": "WE3342",
#     "plate_image_url": "abcd"
# }
