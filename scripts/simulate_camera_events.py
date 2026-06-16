#!/usr/bin/env python3
"""Send synthetic camera events to a ParkPilot backend.

This is a local development stand-in for the Orange Pi / edge detector. It
does not read video frames. It sends the same JSON shape the backend expects
from a detector so dashboards can prove that ingestion, persistence, and
analytics wiring work end to end.
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass, field
from typing import Iterable

import requests


DEFAULT_API_URL = "http://127.0.0.1:8000"


@dataclass
class LotState:
    lot_id: str
    total_spaces: int
    occupied: set[int] = field(default_factory=set)

    @classmethod
    def with_initial_occupancy(
        cls,
        lot_id: str,
        total_spaces: int,
        occupied_count: int,
    ) -> "LotState":
        occupied_count = max(0, min(occupied_count, total_spaces))
        occupied = set(random.sample(range(1, total_spaces + 1), occupied_count))
        return cls(lot_id=lot_id, total_spaces=total_spaces, occupied=occupied)

    def mutate(self, max_changes: int) -> list[dict[str, str]]:
        change_count = random.randint(1, max(1, max_changes))
        changed_spots: list[dict[str, str]] = []

        for _ in range(change_count):
            spot_number = random.randint(1, self.total_spaces)
            if spot_number in self.occupied:
                self.occupied.remove(spot_number)
                status = "free"
            else:
                self.occupied.add(spot_number)
                status = "occupied"

            changed_spots.append(
                {
                    "spot_id": self.spot_id(spot_number),
                    "status": status,
                }
            )

        return changed_spots

    def all_spots(self) -> list[dict[str, str]]:
        return [
            {
                "spot_id": self.spot_id(spot_number),
                "status": "occupied" if spot_number in self.occupied else "free",
            }
            for spot_number in range(1, self.total_spaces + 1)
        ]

    def snapshot_payload(self, events: list[dict[str, str]]) -> dict:
        occupied_spaces = len(self.occupied)
        return {
            "lot_id": self.lot_id,
            "total_spaces": self.total_spaces,
            "available_spaces": self.total_spaces - occupied_spaces,
            "occupied_spaces": occupied_spaces,
            "confidence": round(random.uniform(0.88, 0.99), 3),
            "processing_time_seconds": round(random.uniform(0.08, 0.35), 3),
            "events": events,
        }

    def spot_id(self, spot_number: int) -> str:
        prefix = "A" if self.lot_id == "CAMT_01" else "B"
        return f"{prefix}{spot_number:02d}"


def normalize_api_url(api_url: str) -> str:
    return api_url.rstrip("/")


def post_json(
    session: requests.Session,
    url: str,
    payload: dict,
    dry_run: bool,
) -> requests.Response | None:
    if dry_run:
        print(f"DRY RUN POST {url}: {payload}")
        return None

    response = session.post(url, json=payload, timeout=10)
    response.raise_for_status()
    return response


def send_heartbeat(
    session: requests.Session,
    api_url: str,
    board_id: str,
    dry_run: bool,
) -> None:
    payload = {
        "board_id": board_id,
        "board_status": "online",
        "camera_1_status": "online",
        "camera_2_status": "online",
        "camera_3_status": "online",
        "camera_4_status": "online",
    }
    post_json(session, f"{api_url}/api/analytics/heartbeat", payload, dry_run)


def send_lot_events(
    session: requests.Session,
    api_url: str,
    lots: Iterable[LotState],
    max_changes: int,
    full_events: bool,
    dry_run: bool,
) -> None:
    for lot in lots:
        events = lot.all_spots() if full_events else lot.mutate(max_changes)
        payload = lot.snapshot_payload(events)
        post_json(session, f"{api_url}/api/analytics/camera/events", payload, dry_run)
        print(
            f"{lot.lot_id}: {payload['occupied_spaces']}/{payload['total_spaces']} "
            f"occupied, sent {len(events)} spot events"
        )


def build_lots(total_spaces: int, initial_occupied: int) -> list[LotState]:
    return [
        LotState.with_initial_occupancy("CAMT_01", total_spaces, initial_occupied),
        LotState.with_initial_occupancy("CAMT_02", total_spaces, initial_occupied),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate Orange Pi camera event ingestion for local ParkPilot development."
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Backend base URL. Default: {DEFAULT_API_URL}",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Seconds between simulation ticks. Default: 5",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of ticks to send. Use 0 to run forever. Default: 1",
    )
    parser.add_argument(
        "--total-spaces",
        type=int,
        default=30,
        help="Total spaces per simulated lot. Default: 30",
    )
    parser.add_argument(
        "--initial-occupied",
        type=int,
        default=12,
        help="Initial occupied spaces per lot. Default: 12",
    )
    parser.add_argument(
        "--max-changes",
        type=int,
        default=3,
        help="Maximum spot state flips per tick after the first tick. Default: 3",
    )
    parser.add_argument(
        "--board-id",
        default="orange_pi_main",
        help="Board id to update in device health. Default: orange_pi_main",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payloads without sending them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_url = normalize_api_url(args.api_url)
    lots = build_lots(args.total_spaces, args.initial_occupied)
    session = requests.Session()
    tick = 0

    print(f"Sending simulated camera events to {api_url}")
    print("Press Ctrl+C to stop.")

    while args.count == 0 or tick < args.count:
        tick += 1
        print(f"\nTick {tick}")
        send_heartbeat(session, api_url, args.board_id, args.dry_run)
        send_lot_events(
            session=session,
            api_url=api_url,
            lots=lots,
            max_changes=args.max_changes,
            full_events=(tick == 1),
            dry_run=args.dry_run,
        )

        if args.count != 0 and tick >= args.count:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
