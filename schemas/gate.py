from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class GateEventPayload(BaseModel):
    event: Literal["open", "close"]
    event_id: str = Field(min_length=1, max_length=100)
    gate_id: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    vehicle_class: Optional[str] = Field(default=None, max_length=50)
    confidence: Optional[float] = None
    camera: Optional[int] = None
    open_duration_seconds: Optional[float] = None
    open_count_today: Optional[int] = None
    close_count_today: Optional[int] = None
