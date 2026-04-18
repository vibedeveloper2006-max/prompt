"""
models/analytics_models.py
--------------------------
Response schemas for the analytics insights endpoint.
Powers both the attendee insight panel and the staff operations dashboard.
"""

from pydantic import BaseModel, Field
from typing import List


class LiveZoneStatus(BaseModel):
    """Current live density reading for a single zone."""

    zone_id: str = Field(..., description="Zone identifier (e.g. 'A', 'FC', 'ST')")
    name: str = Field(..., description="Human-readable zone name")
    current_density: int = Field(
        ..., description="Current crowd density as % of capacity (0–100)"
    )
    status: str = Field(..., description="Density label: LOW | MEDIUM | HIGH")


class AnalyticsResponse(BaseModel):
    """Aggregated analytics payload returned by GET /analytics/insights."""

    historical_hotspots: List[str] = Field(
        ...,
        description="Ordered list of zone names with the highest historical congestion (from BigQuery).",
    )
    live_leaderboard: List[LiveZoneStatus] = Field(
        ...,
        description="All zones sorted by current density, highest first.",
    )
    recommended_entry: str = Field(
        ...,
        description="Name of the gate zone currently with the lowest crowd density.",
    )
