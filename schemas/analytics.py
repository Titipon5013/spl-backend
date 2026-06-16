from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# ==========================================
# 1. Heatmap Schemas (คงเดิม)
# ==========================================
class HeatmapSpotResponse(BaseModel):
    spot_id: str
    total_events: int
    occupied_events: int
    occupancy_percentage: float

class HeatmapResponse(BaseModel):
    lot_id: str
    spots: List[HeatmapSpotResponse]

# ==========================================
# 2. Trends Schemas (คงเดิม)
# ==========================================
class TrendDataPoint(BaseModel):
    time_label: str
    average_occupancy: float

class TrendResponse(BaseModel):
    lot_id: str
    peak_hour: Optional[str] = None
    trends: List[TrendDataPoint]

class DeviceStatus(BaseModel):
    status: str
    last_seen: Optional[datetime] = None

class SystemHealthResponse(BaseModel):
    system_status: str
    uptime_percentage: float
    board: DeviceStatus
    camera_1: DeviceStatus
    camera_2: DeviceStatus
    camera_3: DeviceStatus
    camera_4: DeviceStatus

class DeviceHeartbeatPayload(BaseModel):
    board_id: str = "orange_pi_main"
    board_status: str
    camera_1_status: str
    camera_2_status: str
    camera_3_status: str = "offline"
    camera_4_status: str = "offline"

class SpotEvent(BaseModel):
    spot_id: str
    status: str

class CameraEventPayload(BaseModel):
    lot_id: str
    total_spaces: int
    available_spaces: int
    occupied_spaces: int
    confidence: float = 1.0
    processing_time_seconds: float = 0.0
    events: List[SpotEvent]
