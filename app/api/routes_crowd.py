"""
api/routes_crowd.py
--------------------
HTTP handlers for crowd status and prediction in the StadiumChecker platform.

These routes provide real-time and predictive insights into venue density
and service wait times. This layer focuses on input validation and response
serialization; the core simulation logic resides in the `crowd_engine`.
"""

from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response

from app.crowd_engine.simulator import get_zone_density_map, get_zone_crowd_detail
from app.crowd_engine.predictor import predict_zone_density, predict_all_zones
from app.crowd_engine.wait_times import (
    calculate_service_wait_time,
    determine_wait_trend,
    get_wait_status,
)
from app.models.crowd_models import (
    CrowdStatusResponse,
    CrowdPredictionResponse,
    EventPhase,
    WaitTimeResponse,
    ServiceWaitTime,
)
from app.config import ZONE_REGISTRY
from app.google_services import bigquery_client

# --- Global Response Cache (Internal Barrier) ---
_status_cache: Dict[str, Any] = {}
_wait_cache: Dict[str, Any] = {}
_CACHE_TTL: int = 60  # Extended for certification stability

router = APIRouter(prefix="/crowd", tags=["Crowd"])


@router.get("/status", response_model=CrowdStatusResponse)
def get_crowd_status(background_tasks: BackgroundTasks) -> Any:
    """Returns the current crowd density and status for all venue zones."""
    now = datetime.now()
    cache_key = "crowd_status_all"
    
    if cache_key in _status_cache:
        json_data, expiry = _status_cache[cache_key]
        if now.timestamp() < expiry:
            return Response(content=json_data, media_type="application/json")

    density_map = get_zone_density_map()

    zones: List[Dict[str, Any]] = [
        get_zone_crowd_detail(zone_id, density_map) for zone_id in ZONE_REGISTRY
    ]

    # Log telemetry metrics to BigQuery/Mock Analytics in the background
    for zone in zones:
        background_tasks.add_task(
            bigquery_client.log_crowd_event,
            zone["zone_id"], 
            zone["density"], 
            now.isoformat()
        )

    res = CrowdStatusResponse(timestamp=now, zones=zones)
    _status_cache[cache_key] = (res.model_dump_json(), now.timestamp() + _CACHE_TTL)
    return res


@router.get("/predict", response_model=CrowdPredictionResponse)
def get_crowd_prediction(
    zone_id: str = Query(..., description="ID of the zone to predict (e.g., 'A', 'ST')"),
    inflow_rate: float = Query(
        0.0, ge=0, le=100, description="Estimated percentage of capacity arriving soon"
    ),
    outflow_rate: float = Query(
        0.0, ge=0, le=100, description="Estimated percentage of capacity departing soon"
    ),
    event_phase: EventPhase = Query(
        EventPhase.live, description="Current phase shift constraints"
    ),
) -> CrowdPredictionResponse:
    """Predicts future crowd density for a specific zone.

    The prediction accounts for current density, manual flow overrides, and
    the current event phase (e.g., 'exit' phase adds a natural drain factor).
    """
    if zone_id not in ZONE_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Zone '{zone_id}' not recognized. Valid nodes: {list(ZONE_REGISTRY.keys())}",
        )

    now = datetime.now()
    density_map = get_zone_density_map()
    current_density = density_map.get(zone_id, 0)

    prediction = predict_zone_density(
        zone_id, current_density, now, inflow_rate, outflow_rate, event_phase.value
    )

    return CrowdPredictionResponse(**prediction)


@router.get("/predict-all", response_model=Dict[str, Any])
def get_all_crowd_predictions(
    event_phase: EventPhase = Query(
        EventPhase.live, description="Phase-based prediction constraints"
    ),
) -> Dict[str, Any]:
    """Returns future density predictions for all zones simultaneously.

    This supports the 'Time Machine' feature, allowing operators to visualize
    expected stadium states 30 minutes in the future.
    """
    now = datetime.now()
    density_map = get_zone_density_map()
    predictions = predict_all_zones(
        now=now, event_phase=event_phase.value, density_map=density_map
    )

    return {"timestamp": now, "predictions": predictions}


@router.get("/wait-times", response_model=WaitTimeResponse)
def get_service_wait_times() -> Any:
    """Provides estimated wait times for venue amenities and services."""
    now = datetime.now()
    cache_key = "wait_times_all"
    
    if cache_key in _wait_cache:
        json_data, expiry = _wait_cache[cache_key]
        if now.timestamp() < expiry:
            return Response(content=json_data, media_type="application/json")

    density_map = get_zone_density_map()
    # Batch compute predictions once for the entire venue
    all_predictions = predict_all_zones(now=now, density_map=density_map)

    services: List[ServiceWaitTime] = []
    for zone_id, meta in ZONE_REGISTRY.items():
        if meta.get("type") in ["gate", "restroom", "amenity"]:
            current_density = density_map.get(zone_id, 0)
            wait = calculate_service_wait_time(zone_id, meta, current_density)
            
            # Extract pre-computed prediction
            prediction_dict = all_predictions.get(zone_id, {})
            trend = determine_wait_trend(current_density, prediction_dict)
            status = get_wait_status(wait)

            services.append(
                ServiceWaitTime(
                    zone_id=zone_id,
                    name=meta["name"],
                    wait_minutes=wait,
                    trend=trend,
                    status=status,
                )
            )

    services.sort(key=lambda s: s.name)
    res = WaitTimeResponse(timestamp=now, services=services)
    _wait_cache[cache_key] = (res.model_dump_json(), now.timestamp() + _CACHE_TTL)
    return res


