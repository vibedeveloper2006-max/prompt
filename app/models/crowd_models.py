"""
models/crowd_models.py
----------------------
Pydantic schemas for crowd-related telemetry and predictions.
"""

from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class EventPhase(str, Enum):
    """Represents the current phase of the event, affecting crowd dynamics."""

    entry = "entry"
    live = "live"
    halftime = "halftime"
    exit = "exit"


class ZoneCrowdStatus(BaseModel):
    """Current density and status level of a specific venue zone."""

    zone_id: str = Field(
        ..., description="Unique shorthand ID for the zone (e.g. 'A1', 'FC')"
    )
    name: str = Field(..., description="Human-readable name of the zone")
    density: int = Field(
        ...,
        ge=0,
        le=100,
        description="Crowd density as a percentage (0-100%)",
        example=45,
    )
    status: str = Field(
        ...,
        description="Categorical status: LOW (0-39), MEDIUM (40-69), or HIGH (70+)",
        example="MEDIUM",
    )


class CrowdStatusResponse(BaseModel):
    """Response containing live density data for all stadium nodes."""

    timestamp: datetime = Field(
        ..., description="Server-side time when the snapshot was generated"
    )
    zones: List[ZoneCrowdStatus] = Field(
        ..., description="List of all zone status objects"
    )


class CrowdPredictionResponse(BaseModel):
    """Predictive snapshot for a zone based on flow heuristics and event phase."""

    zone_id: str = Field(..., description="ID of the predicted zone")
    current_density: int = Field(..., description="Starting density percentage")
    predicted_density: int = Field(
        ..., description="Predicted density percentage in 30 minutes"
    )
    trend: str = Field(
        ..., description="Directional movement: INCREASING | STABLE | DECREASING"
    )
    prediction_window_minutes: int = Field(
        30, description="Look-ahead duration in minutes"
    )
    inflow_rate: float = Field(0.0, description="Manual entry rate override (%)")
    flow_delta: int = Field(0, description="Net change in density points")


class ServiceWaitTime(BaseModel):
    """Estimated queue or delay metrics for a specific venue service."""

    zone_id: str = Field(..., description="ID of the service zone")
    name: str = Field(..., description="Human-readable service name (e.g. 'Gate A')")
    wait_minutes: int = Field(..., description="Estimated wait time in minutes")
    trend: str = Field(
        ..., description="Wait time trend: INCREASING | DECREASING | STABLE"
    )
    status: str = Field(..., description="Availability status: LOW | MODERATE | HIGH")


class WaitTimeResponse(BaseModel):
    """Response containing live service availability and wait-time estimations."""

    timestamp: datetime = Field(..., description="Generation timestamp")
    services: List[ServiceWaitTime] = Field(
        ..., description="List of service wait-time objects"
    )
