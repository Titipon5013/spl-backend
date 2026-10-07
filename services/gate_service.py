from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import GateEvent
from schemas.gate import GateEventPayload


class GateService:
    LOCAL_TIMEZONE = ZoneInfo("Asia/Bangkok")

    def __init__(self, db: Session):
        self.db = db

    def record_event(self, payload: GateEventPayload) -> str:
        event_timestamp = payload.timestamp
        if event_timestamp.tzinfo is None:
            event_timestamp = event_timestamp.replace(tzinfo=self.LOCAL_TIMEZONE)
        event_timestamp = event_timestamp.astimezone(timezone.utc)

        event = GateEvent(
            event=payload.event,
            event_id=payload.event_id,
            gate_id=payload.gate_id,
            vehicle_class=payload.vehicle_class,
            confidence=payload.confidence,
            timestamp=event_timestamp,
        )
        self.db.add(event)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = (
                self.db.query(GateEvent)
                .filter(GateEvent.event_id == payload.event_id)
                .first()
            )
            if existing is not None:
                return "duplicate_ignored"
            raise
        return "saved"

    def get_count(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[str, int | bool]:
        events = (
            self.db.query(GateEvent.event)
            .filter(GateEvent.timestamp >= start, GateEvent.timestamp < end)
            .all()
        )
        open_count = sum(event.event == "open" for event in events)
        close_count = sum(event.event == "close" for event in events)
        count_gap = open_count - close_count
        return {
            "open_count": open_count,
            "close_count": close_count,
            "count_gap": count_gap,
            "has_missing_message": abs(count_gap) > 1,
        }

    def get_daily_count(self, day: date | None = None) -> dict[str, int | bool]:
        current_day = day or datetime.now(self.LOCAL_TIMEZONE).date()
        local_start = datetime.combine(current_day, time.min, self.LOCAL_TIMEZONE)
        start = local_start.astimezone(timezone.utc)
        return self.get_count(start, start + timedelta(days=1))

    def get_hourly_counts(self, day: date | None = None) -> list[dict[str, object]]:
        current_day = day or datetime.now(self.LOCAL_TIMEZONE).date()
        local_start = datetime.combine(current_day, time.min, self.LOCAL_TIMEZONE)
        result = []
        for hour in range(24):
            local_hour = local_start + timedelta(hours=hour)
            start = local_hour.astimezone(timezone.utc)
            result.append(
                {
                    "hour": local_hour.strftime("%H:00"),
                    **self.get_count(start, start + timedelta(hours=1)),
                }
            )
        return result

    def get_weekly_summary(
        self, week_start: date | None = None
    ) -> dict[str, object]:
        current_day = week_start or datetime.now(self.LOCAL_TIMEZONE).date()
        monday = current_day - timedelta(days=current_day.weekday())
        local_start = datetime.combine(monday, time.min, self.LOCAL_TIMEZONE)
        start = local_start.astimezone(timezone.utc)
        end = (local_start + timedelta(days=7)).astimezone(timezone.utc)

        events = (
            self.db.query(GateEvent.event, GateEvent.timestamp)
            .filter(GateEvent.timestamp >= start, GateEvent.timestamp < end)
            .all()
        )
        daily_counts: dict[date, dict[str, int]] = defaultdict(
            lambda: {"open_count": 0, "close_count": 0}
        )
        hourly_counts: dict[int, dict[str, int]] = defaultdict(
            lambda: {"open_count": 0, "close_count": 0}
        )
        for event in events:
            local_timestamp = event.timestamp
            if local_timestamp.tzinfo is None:
                local_timestamp = local_timestamp.replace(tzinfo=timezone.utc)
            local_timestamp = local_timestamp.astimezone(self.LOCAL_TIMEZONE)
            event_day = daily_counts[local_timestamp.date()]
            event_hour = hourly_counts[local_timestamp.hour]
            event_day[f"{event.event}_count"] += 1
            event_hour[f"{event.event}_count"] += 1

        daily = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            counts = daily_counts[day]
            count_gap = counts["open_count"] - counts["close_count"]
            daily.append(
                {
                    "date": day,
                    **counts,
                    "count_gap": count_gap,
                    "has_missing_message": abs(count_gap) > 1,
                }
            )

        def peak(event_name: str) -> dict[str, object] | None:
            if not hourly_counts:
                return None
            hour, counts = max(
                hourly_counts.items(),
                key=lambda item: (item[1][f"{event_name}_count"], -item[0]),
            )
            return {
                "hour": f"{hour:02d}:00",
                "count": counts[f"{event_name}_count"],
            }

        open_count = sum(item["open_count"] for item in daily)
        close_count = sum(item["close_count"] for item in daily)
        count_gap = open_count - close_count
        peak_total_hour, peak_total_counts = max(
            hourly_counts.items(),
            key=lambda item: (
                item[1]["open_count"] + item[1]["close_count"],
                -item[0],
            ),
            default=(None, {"open_count": 0, "close_count": 0}),
        )
        return {
            "start_date": monday,
            "end_date": monday + timedelta(days=6),
            "open_count": open_count,
            "close_count": close_count,
            "count_gap": count_gap,
            "has_missing_message": abs(count_gap) > 1,
            "daily": daily,
            "peak_hours": {
                "open": peak("open"),
                "close": peak("close"),
                "total": (
                    {
                        "hour": f"{peak_total_hour:02d}:00",
                        "count": peak_total_counts["open_count"]
                        + peak_total_counts["close_count"],
                    }
                    if peak_total_hour is not None
                    else None
                ),
            },
        }
