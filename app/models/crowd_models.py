"""
models/crowd_models.py
----------------------
Pydantic schemas for crowd-related data.
"""

from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from enum import Enum


class EventPhase(str, Enum):
    entry = "entry"
    live = "live"
    halftime = "halftime"
    exit = "exit"


class ZoneCrowdStatus(BaseModel):
    zone_id: str
    name: str
    density: int = Field(..., ge=0, le=100, description="Crowd density 0-100%")
    status: str  # LOW | MEDIUM | HIGH


class CrowdStatusResponse(BaseModel):
    timestamp: datetime
    zones: List[ZoneCrowdStatus]


class CrowdPredictionResponse(BaseModel):
    zone_id: str
    current_density: int
    predicted_density: int
    trend: str  # INCREASING | STABLE | DECREASING
    prediction_window_minutes: int = 30
    # Flow diagnostics (0.0 when not provided by caller)
    inflow_rate: float = 0.0
    flow_delta: int = 0

class ServiceWaitTime(BaseModel):
    zone_id: str
    name: str
    wait_minutes: int
    trend: str # INCREASING, DECREASING, STABLE
    status: str # LOW, MODERATE, HIGH
    
class WaitTimeResponse(BaseModel):
    timestamp: datetime
    services: List[ServiceWaitTime]
