from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GateEventPayload(BaseModel):
    event: Literal["open", "close"]
    event_id: str = Field(min_length=1, max_length=100)
    gate_id: str = Field(min_length=1, max_length=50)
    vehicle_class: str | None = Field(default=None, max_length=30)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    timestamp: datetime


class GateCountResponse(BaseModel):
    open_count: int
    close_count: int
    count_gap: int
    has_missing_message: bool
