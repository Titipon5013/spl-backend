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

# ==========================================
# 3. System Health Schemas (แก้ใหม่ให้รองรับ 1 บอร์ด 2 กล้อง)
# ==========================================
class DeviceStatus(BaseModel):
    status: str                         # "online" หรือ "offline"
    last_seen: Optional[datetime] = None

class SystemHealthResponse(BaseModel):
    system_status: str                  # "Healthy", "Degraded", หรือ "Critical"
    uptime_percentage: float
    board: DeviceStatus                 # สถานะของ Orange Pi
    camera_1: DeviceStatus              # สถานะของกล้องตัวที่ 1
    camera_2: DeviceStatus              # สถานะของกล้องตัวที่ 2

# ==========================================
# 4. Hardware Ingestion Schemas (เพิ่ม Heartbeat)
# ==========================================
class DeviceHeartbeatPayload(BaseModel):
    board_id: str = "orange_pi_main"
    board_status: str                   # "online"
    camera_1_status: str                # "online" หรือ "offline"
    camera_2_status: str                # "online" หรือ "offline"

class SpotEvent(BaseModel):
    spot_id: str
    status: str

class CameraEventPayload(BaseModel):
    lot_id: str
    total_spaces: int
    available_spaces: int
    occupied_spaces: int
    events: List[SpotEvent]