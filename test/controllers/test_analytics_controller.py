from datetime import datetime, timedelta

import pytest
from db.models import (
    DeviceHealth,
    EntryRecord,
    ParkingEventLog,
    ParkingSnapshot,
    ParkingSnapshot2,
)


def test_get_current_status(client, db_session):
    snapshot = ParkingSnapshot(
        lot_id="CAMT_01",
        timestamp=datetime.utcnow(),
        available_spaces=20,
        total_spaces=30,
        occupied_spaces=10,
        occupacy_rate=33.3,
        confidence=0.9,
        processing_time_seconds=0.1,
    )
    db_session.add(snapshot)
    db_session.commit()

    response = client.get("/api/analytics/current?lot_id=CAMT_01")
    assert response.status_code == 200
    assert response.json()["occupied_spaces"] == 10


def test_get_kpis_with_events(client, db_session):
    now = datetime.utcnow()
    db_session.add(
        ParkingEventLog(
            lot_id="CAMT_01",
            spot_id="A1",
            is_occupied=True,
            timestamp=now - timedelta(minutes=30),
        )
    )
    db_session.add(
        ParkingEventLog(
            lot_id="CAMT_01",
            spot_id="A1",
            is_occupied=False,
            timestamp=now - timedelta(minutes=10),
        )
    )
    db_session.add(
        EntryRecord(
            plate_number="ABC-123",
            plate_image_url="http://example.com/img.jpg",
            timestamp=now,
        )
    )
    db_session.commit()

    response = client.get(
        "/api/analytics/kpis",
        params={
            "lot_id": "CAMT_01",
            "start_date": (now - timedelta(days=1)).isoformat(),
            "end_date": now.isoformat(),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["vehicle_count"] == 1
    assert data["avg_dwell_time_minutes"] == 20.0


def test_get_occupancy_trends(client, db_session):
    now = datetime.utcnow().replace(minute=15, second=0, microsecond=0)
    db_session.add_all(
        [
            ParkingSnapshot(
                lot_id="CAMT_01",
                timestamp=now - timedelta(hours=1),
                available_spaces=20,
                total_spaces=30,
                occupied_spaces=10,
                occupacy_rate=33.3,
                confidence=0.9,
                processing_time_seconds=0.1,
            ),
            ParkingSnapshot(
                lot_id="CAMT_01",
                timestamp=now,
                available_spaces=12,
                total_spaces=30,
                occupied_spaces=18,
                occupacy_rate=60.0,
                confidence=0.9,
                processing_time_seconds=0.1,
            ),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/analytics/trends",
        params={
            "lot_id": "CAMT_01",
            "start_date": (now - timedelta(days=1)).isoformat(),
            "end_date": (now + timedelta(minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["peak_hour"] == now.strftime("%Y-%m-%d %H:00")
    assert len(data["trends"]) == 2


def test_get_heatmap_groups_events_by_spot(client, db_session):
    now = datetime.utcnow()
    db_session.add_all(
        [
            ParkingEventLog(
                lot_id="CAMT_01",
                spot_id="A1",
                is_occupied=True,
                timestamp=now - timedelta(minutes=3),
            ),
            ParkingEventLog(
                lot_id="CAMT_01",
                spot_id="A1",
                is_occupied=False,
                timestamp=now - timedelta(minutes=2),
            ),
            ParkingEventLog(
                lot_id="CAMT_01",
                spot_id="A2",
                is_occupied=True,
                timestamp=now - timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/analytics/heatmap?lot_id=CAMT_01")

    assert response.status_code == 200
    spots = {spot["spot_id"]: spot for spot in response.json()["spots"]}
    assert spots["A1"]["occupancy_percentage"] == 50.0
    assert spots["A2"]["occupancy_percentage"] == 100.0


def test_get_slot_event_history(client, db_session):
    now = datetime.utcnow()
    db_session.add(
        ParkingEventLog(
            lot_id="CAMT_01",
            spot_id="B2",
            is_occupied=True,
            timestamp=now,
        )
    )
    db_session.commit()

    response = client.get("/api/analytics/slots/B2/events?lot_id=CAMT_01")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["state"] == "occupied"


def test_system_health_uptime(client, db_session):
    db_session.add(
        DeviceHealth(
            device_id="board_main",
            device_type="board",
            status="online",
            last_seen=datetime.utcnow(),
        )
    )
    db_session.commit()

    response = client.get("/api/analytics/health?lot_id=CAMT_01")
    assert response.status_code == 200
    assert response.json()["uptime_percentage"] >= 0


def test_heartbeat_updates_four_camera_streams(client, db_session):
    response = client.post(
        "/api/heartbeat",
        json={
            "board_id": "orange_pi_main",
            "board_status": "online",
            "camera_1_status": "online",
            "camera_2_status": "online",
            "camera_3_status": "online",
            "camera_4_status": "offline",
        },
    )

    assert response.status_code == 200

    health_response = client.get("/api/analytics/health?lot_id=CAMT_01")
    assert health_response.status_code == 200
    data = health_response.json()
    assert data["system_status"] == "Degraded"
    assert data["camera_1"]["status"] == "online"
    assert data["camera_2"]["status"] == "online"
    assert data["camera_3"]["status"] == "online"
    assert data["camera_4"]["status"] == "offline"


def test_camera_event_ingestion_appends_logs_and_snapshot(client, db_session):
    response = client.post(
        "/api/camera/events",
        json={
            "lot_id": "CAMT_01",
            "total_spaces": 30,
            "available_spaces": 18,
            "occupied_spaces": 12,
            "confidence": 0.95,
            "processing_time_seconds": 0.2,
            "events": [
                {"spot_id": "A1", "status": "occupied"},
                {"spot_id": "A2", "status": "free"},
            ],
        },
    )

    assert response.status_code == 201
    assert db_session.query(ParkingEventLog).count() == 2
    snapshot = db_session.query(ParkingSnapshot).first()
    assert snapshot.occupied_spaces == 12
    assert snapshot.confidence == 0.95


def test_sync_snapshot_distributes_occupancy_to_camt02_slots(client, db_session):
    # TC: POST /api/analytics/sync — กระจายยอด 34 ช่องตามพิกัดจริงของ CAMT_02
    response = client.post(
        "/api/analytics/sync",
        json={
            "lot_id": "CAMT_02",
            "total_spaces": 34,
            "available_spaces": 14,
            "occupied_spaces": 20,
            "occupacy_rate": 58.82,
            "confidence": 0.97,
            "processing_time_seconds": 0.12,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    snapshot = db_session.query(ParkingSnapshot2).first()
    assert snapshot is not None
    assert snapshot.occupied_spaces == 20
    assert snapshot.available_spaces == 14
    assert snapshot.occupacy_rate == pytest.approx(58.82)

    events = (
        db_session.query(ParkingEventLog)
        .filter(ParkingEventLog.lot_id == "CAMT_02")
        .all()
    )
    assert len(events) == 34
    occupied = [e for e in events if e.is_occupied]
    assert len(occupied) == 20
    occupied_ids = {e.spot_id for e in occupied}
    assert "A1" in occupied_ids
    assert "A13" in occupied_ids
    assert "C15" not in occupied_ids


def test_sync_snapshot_marks_board_online(client, db_session):
    # TC: /sync ต้องอัปเดต DeviceHealth ของ orange_pi_main เป็น online
    response = client.post(
        "/api/analytics/sync",
        json={
            "lot_id": "CAMT_01",
            "total_spaces": 30,
            "available_spaces": 18,
            "occupied_spaces": 12,
            "occupacy_rate": 40.0,
        },
    )

    assert response.status_code == 200

    board = (
        db_session.query(DeviceHealth)
        .filter(DeviceHealth.device_id == "orange_pi_main")
        .first()
    )
    assert board is not None
    assert board.status == "online"
    assert board.last_seen is not None

    # CAMT_01 จำลองช่องเป็น Spot_01..N ตาม total_spaces
    events = (
        db_session.query(ParkingEventLog)
        .filter(ParkingEventLog.lot_id == "CAMT_01")
        .all()
    )
    assert len(events) == 30
    assert {e.spot_id for e in events if e.is_occupied} == {
        f"Spot_{str(i).zfill(2)}" for i in range(1, 13)
    }
