from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from db.models import ParkingEventLog, ParkingSnapshot, ParkingSnapshot2
from schemas.analytics import HeatmapSpotResponse, HeatmapResponse, TrendResponse, TrendDataPoint
from datetime import datetime
from typing import Optional
from collections import defaultdict


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def get_heatmap_data(self, lot_id: str, start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> HeatmapResponse:

        query = self.db.query(
            ParkingEventLog.spot_id,
            func.count(ParkingEventLog.id).label('total'),
            func.sum(cast(ParkingEventLog.is_occupied, Integer)).label('occupied')
        ).filter(ParkingEventLog.spot_id.startswith(lot_id))

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
                spot_id=spot_id.replace(f"{lot_id}_", ""),
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

