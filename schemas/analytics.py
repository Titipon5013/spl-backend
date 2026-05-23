from pydantic import BaseModel
from typing import List, Optional

class HeatmapSpotResponse(BaseModel):
    spot_id: str
    total_events: int
    occupied_events: int
    occupancy_percentage: float

class HeatmapResponse(BaseModel):
    lot_id: str
    spots: List[HeatmapSpotResponse]

class TrendDataPoint(BaseModel):
    time_label: str
    average_occupancy: float

class TrendResponse(BaseModel):
    lot_id: str
    peak_hour: Optional[str] = None
    trends: List[TrendDataPoint]