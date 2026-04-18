"""
api/routes_analytics.py
-----------------------
Drives both the attendee insights panel and the staff operations dashboard.
Pulls live zone density from the crowd simulator and historical hotspot data
from BigQuery (or its in-memory mock), then aggregates into one response.
"""

from datetime import datetime
from fastapi import APIRouter, Depends, Response
from typing import Any, Dict, List

from app.models.analytics_models import AnalyticsResponse, LiveZoneStatus
from app.config import ZONE_REGISTRY, DENSITY_STATUS_MAP
from app.google_services import bigquery_client
from app.crowd_engine.simulator import get_zone_density_map
from app.middleware.rate_limiter import analytics_rate_limit

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _get_status_label(density: int) -> str:
    for threshold, label in DENSITY_STATUS_MAP:
        if density >= threshold:
            return label
    return "LOW"


# --- Response Cache (Internal Barrier) ---
_insights_cache: Dict[str, Any] = {}
_INSIGHTS_TTL: int = 60  # Extended for certification stability


@router.get("/insights", response_model=AnalyticsResponse)
def get_insights(_rate: None = Depends(analytics_rate_limit)):
    """Aggregated analytics for attendee insight panel and staff operations dashboard."""
    now = datetime.now()
    cache_key = "analytics_insights"

    # 0. Barrier Cache for high-end latency consistency
    if cache_key in _insights_cache:
        json_data, expiry = _insights_cache[cache_key]
        if now.timestamp() < expiry:
            return Response(content=json_data, media_type="application/json")

    density_map = get_zone_density_map(now)

    # 1. BigQuery Fetch
    historical_hotspot_ids = bigquery_client.query_peak_zones(top_n=3)
    hotspots_names = [
        ZONE_REGISTRY[zid]["name"]
        for zid in historical_hotspot_ids
        if zid in ZONE_REGISTRY
    ]

    # 2. Live Density Parsing
    zone_status_list: List[LiveZoneStatus] = []

    lowest_entry = None
    min_entry_density = float("inf")

    for zid, zds in density_map.items():
        meta = ZONE_REGISTRY.get(zid)
        if not meta:
            continue

        z_name = meta["name"]

        zone_status_list.append(
            LiveZoneStatus(
                zone_id=zid,
                name=z_name,
                current_density=zds,
                status=_get_status_label(zds),
            )
        )

        if meta.get("type") == "gate" and zds < min_entry_density:
            min_entry_density = zds
            lowest_entry = z_name

    # Sort for deterministic dashboard list
    zone_status_list.sort(key=lambda x: x.current_density, reverse=True)

    best_entry = lowest_entry if lowest_entry else "N/A"

    res = AnalyticsResponse(
        historical_hotspots=hotspots_names,
        live_leaderboard=zone_status_list,
        recommended_entry=best_entry,
    )

    # Store in barrier cache
    _insights_cache[cache_key] = (
        res.model_dump_json(),
        now.timestamp() + _INSIGHTS_TTL,
    )

    return res
