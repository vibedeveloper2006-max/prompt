"""
api/routes_crowd.py
--------------------
HTTP handlers for crowd status and prediction.

Thin layer — validates input, calls crowd_engine, returns response.
No business logic lives here.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query

from app.crowd_engine.simulator import get_zone_density_map, get_zone_crowd_detail
from app.crowd_engine.predictor import predict_zone_density, predict_all_zones
from app.crowd_engine.wait_times import calculate_service_wait_time, determine_wait_trend, get_wait_status
from app.models.crowd_models import CrowdStatusResponse, CrowdPredictionResponse, EventPhase, WaitTimeResponse, ServiceWaitTime
from app.config import ZONE_REGISTRY
from app.google_services import bigquery_client

router = APIRouter(prefix="/crowd", tags=["Crowd"])


@router.get("/status", response_model=CrowdStatusResponse)
def get_crowd_status():
    """
    Returns current crowd density for ALL zones.
    Also logs a snapshot to BigQuery for analytics.

    get_zone_density_map() is called without `now` so it benefits from the
    2-second shared cache — the same computation is reused across burst calls
    (e.g. /crowd/status → /crowd/wait-times within the same polling cycle).
    """
    now = datetime.now()
    density_map = get_zone_density_map()  # cache-eligible — no explicit `now`

    zones = [
        get_zone_crowd_detail(zone_id, density_map)
        for zone_id in ZONE_REGISTRY
    ]

    # Log to BigQuery (mock) for analytics
    for zone in zones:
        bigquery_client.log_crowd_event(zone["zone_id"], zone["density"], now.isoformat())

    return CrowdStatusResponse(timestamp=now, zones=zones)


@router.get("/predict", response_model=CrowdPredictionResponse)
def get_crowd_prediction(
    zone_id: str = Query(..., description="Zone ID to predict (e.g. A, FC, ST)"),
    inflow_rate: float = Query(0.0, ge=0, le=100, description="% of zone capacity arriving in next 30 min"),
    outflow_rate: float = Query(0.0, ge=0, le=100, description="% of zone capacity leaving in next 30 min"),
    event_phase: EventPhase = Query(EventPhase.live, description="Current event phase constraint"),
):
    """
    Predicts crowd density for a specific zone 30 minutes from now.

    Combines peak-hour time rules with optional flow rates:
      - inflow_rate: how fast people are entering the zone
      - outflow_rate: how fast people are leaving

    Both default to 0 (pure time-based prediction when omitted).
    """
    if zone_id not in ZONE_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Zone '{zone_id}' not found. Valid zones: {list(ZONE_REGISTRY.keys())}",
        )

    now = datetime.now()
    density_map = get_zone_density_map()  # cache-eligible — no explicit `now`
    current_density = density_map[zone_id]
    prediction = predict_zone_density(
        zone_id, current_density, now, inflow_rate, outflow_rate, event_phase.value
    )

    return CrowdPredictionResponse(**prediction)


@router.get("/predict-all")
def get_all_crowd_predictions(
    event_phase: EventPhase = Query(EventPhase.live, description="Current event phase constraint"),
):
    """
    Returns predictions for ALL zones 30 minutes from now.
    Used by the Time Machine feature to visualize future stadium states.
    """
    now = datetime.now()
    density_map = get_zone_density_map()
    predictions = predict_all_zones(now=now, event_phase=event_phase.value, density_map=density_map)
    
    return {
        "timestamp": now,
        "predictions": predictions
    }

@router.get("/wait-times", response_model=WaitTimeResponse)
def get_service_wait_times():
    """
    Returns live wait-time estimates for specific venue services 
    (gates, restrooms, food courts, exits).

    get_zone_density_map is called without `now` so it benefits from the
    2-second shared cache — the same map computed by /crowd/status moments
    ago is reused here rather than recomputed.
    """
    now = datetime.now()
    density_map = get_zone_density_map()   # cache-eligible — no explicit `now`
    
    services = []
    for zone_id, meta in ZONE_REGISTRY.items():
        if meta.get("type") in ["gate", "restroom", "amenity"]:
            current_density = density_map.get(zone_id, 0)
            wait = calculate_service_wait_time(zone_id, meta, current_density)
            
            # Predict 30 min out for trend direction
            # Pass current_density explicitly — predict_zone_density only needs
            # the zone's density number, not the whole map
            prediction = predict_zone_density(zone_id, current_density, now, 0, 0, EventPhase.live.value)
            trend = determine_wait_trend(current_density, prediction)
            status = get_wait_status(wait)
            
            services.append(
                ServiceWaitTime(
                    zone_id=zone_id,
                    name=meta["name"],
                    wait_minutes=wait,
                    trend=trend,
                    status=status
                )
            )
            
    # Sort services alphabetically for consistent, predictable API responses
    services.sort(key=lambda s: s.name)
    return WaitTimeResponse(timestamp=now, services=services)


