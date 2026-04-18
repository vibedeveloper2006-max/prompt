"""
models/navigation_models.py
----------------------------
Pydantic schemas for navigation request/response.

Security bounds
---------------
- user_id:      max 64 chars.
- current_zone / destination: max 32 chars (longest zone key is 11 chars).
- user_note:    max 256 chars — free-text field; bounded to prevent log injection.
- constraints:  max 5 items — prevents constraint explosion in the router.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum

from app.models.crowd_models import EventPhase


class Priority(str, Enum):
    fast_exit = "fast_exit"
    low_crowd = "low_crowd"
    accessible = "accessible"
    family_friendly = "family_friendly"
    fastest = "fastest"  # Backward compatibility mapped to fast_exit
    least_crowded = "least_crowded"  # Backward compatibility mapped to low_crowd


class NavigationRequest(BaseModel):
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique user identifier",
    )
    current_zone: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Zone where the user currently is",
    )
    destination: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Destination zone ID or name",
    )
    priority: Priority = Priority.fast_exit
    event_phase: EventPhase = EventPhase.live
    constraints: Optional[List[str]] = Field(
        default_factory=lambda: [],
        max_length=5,
        description="List of routing constraints like 'avoid_crowd', 'prefer_fastest'. Max 5.",
    )
    user_note: Optional[str] = Field(
        None,
        max_length=256,
        description="Optional text describing user intent or constraints. Max 256 chars.",
    )


class ZoneScoreDetail(BaseModel):
    score: int
    confidence_score: int


class ReasoningSummary(BaseModel):
    density_factor: float = Field(..., description="Weight/influence of density (0-1)")
    trend_factor: float = Field(
        ..., description="Weight/influence of crowd trends (0-1)"
    )
    event_factor: float = Field(
        ..., description="Weight/influence of event phase (0-1)"
    )


class Waypoint(BaseModel):
    zone_id: str
    lat: float
    lng: float


class NavigationResponse(BaseModel):
    user_id: str
    recommended_route: List[str]
    estimated_wait_minutes: int
    total_walking_distance_meters: int = 0
    route_waypoints: List[Waypoint] = Field(default_factory=list)
    zone_scores: Dict[str, ZoneScoreDetail]  # zone_id → score details
    reasoning_summary: ReasoningSummary
    ai_explanation: Optional[str] = None


class RerouteAlertResponse(BaseModel):
    requires_reroute: bool
    new_navigation: Optional[NavigationResponse] = None
