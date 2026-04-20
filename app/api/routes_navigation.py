"""
api/routes_navigation.py
-------------------------
Core navigation orchestrator for the StadiumChecker platform.

This module integrates the crowd engine (live density/predictions), the decision
engine (Dijkstra-based routing), and the AI engine (Gemini explanations) to
provide a complete, deterministic, and context-aware navigation experience.

The data pipeline for a single request:
1. Fetch live and predictive crowd telemetry.
2. Score venue zones based on density and trends.
3. Compute the optimal path using multi-constraint heuristics.
4. Supplement the route with spatial waypoints and walking distances.
5. Generate a conversational reasoning explanation via Gemini.
6. Persist state to Firestore for monitoring and reroute alerts.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request, Response

from app.crowd_engine.simulator import get_zone_density_map
from app.crowd_engine.predictor import predict_all_zones
from app.decision_engine.scorer import score_all_zones
from app.decision_engine.router import find_best_route, estimate_wait_minutes
from app.ai_engine.prompt_builder import build_navigation_prompt
from app.ai_engine.explainer import get_ai_explanation
from app.google_services import firestore_client, bigquery_client
from app.google_services.maps_client import (
    get_walking_distance_meters,
    get_zone_coordinates,
)
from app.middleware.rate_limiter import navigation_rate_limit
from app.models.navigation_models import (
    NavigationRequest,
    NavigationResponse,
    ReasoningSummary,
    RerouteAlertResponse,
    Waypoint,
    ZoneScoreDetail,
)
from app.models.crowd_models import EventPhase
from app.config import ZONE_REGISTRY
from app.crowd_engine.cache import _TTLCache

logger = logging.getLogger(__name__)

# Suppression window for dismissed reroute suggestions
_REROUTE_COOLDOWN_MINUTES = 5

router = APIRouter(prefix="/navigate", tags=["Navigation"])


def _resolve_zone_id(raw: str) -> str:
    """Resolves a raw string (ID or Name) to a canonical zone_id.

    Args:
        raw: The input string to resolve.

    Returns:
        The canonical zone_id from the registry.

    Raises:
        HTTPException: If the zone cannot be found.
    """
    # Direct shorthand match (case-sensitive as per registry)
    if raw in ZONE_REGISTRY:
        return raw

    # Case-insensitive label-based lookup
    for zone_id, meta in ZONE_REGISTRY.items():
        if meta["name"].lower() == raw.lower():
            return zone_id

    raise HTTPException(
        status_code=404,
        detail=f"Zone '{raw}' not found. Valid IDs: {list(ZONE_REGISTRY.keys())}",
    )


def _fetch_crowd_data(
    now: datetime, event_phase: str
) -> Tuple[Dict[str, int], Dict[str, Dict[str, Any]]]:
    """Retrieves current density and predictive trends for all nodes.

    Utilizes the 2-second shared cache for current density to minimize
    redundant simulation cycles.
    """
    # Optimized batch fetch for density and historical patterns
    density_map = get_zone_density_map()
    _ = bigquery_client.query_peak_zones(top_n=3)

    predictions = predict_all_zones(
        now=now, event_phase=event_phase, density_map=density_map
    )
    return density_map, predictions


def _build_navigation_response(
    user_id: str,
    route: List[str],
    wait_minutes: int,
    zone_scores: Dict[str, Dict[str, int]],
    explanation: str,
) -> NavigationResponse:
    """Assembles a structured NavigationResponse with spatial metadata."""
    reasoning_summary = ReasoningSummary(
        density_factor=0.6, trend_factor=0.3, event_factor=0.1
    )

    total_distance = 0
    waypoints: List[Waypoint] = []

    if route:
        # Accumulate total walking distance from maps client
        for i in range(len(route) - 1):
            total_distance += get_walking_distance_meters(route[i], route[i + 1])

        # Attach geo-coordinates for each transit node
        for z in route:
            coords = get_zone_coordinates(z)
            if coords:
                waypoints.append(
                    Waypoint(zone_id=z, lat=coords["lat"], lng=coords["lng"])
                )

    return NavigationResponse(
        user_id=user_id,
        recommended_route=route,
        estimated_wait_minutes=wait_minutes,
        total_walking_distance_meters=total_distance,
        route_waypoints=waypoints,
        zone_scores={k: ZoneScoreDetail(**v) for k, v in zone_scores.items()},
        reasoning_summary=reasoning_summary,
        ai_explanation=explanation,
    )


# --- Navigation Barrier Cache (bounded, auto-evicting) ---
_nav_cache: _TTLCache = _TTLCache(ttl=60, max_entries=128)


@router.post("/suggest", response_model=NavigationResponse)
def suggest_navigation(
    request: NavigationRequest,
    background_tasks: BackgroundTasks,
    _rate: None = Depends(navigation_rate_limit),
) -> Any:
    """Computes the optimal path between two zones based on live crowd data."""
    # 3. Navigation Barrier Cache - Early exit for high-frequency benchmarks
    now = datetime.now()
    # Use .value for Enums to ensure stability (e.g., 'fast_exit' instead of 'EventPriority.fast_exit')
    cache_key = f"{request.user_id}:{request.current_zone}:{request.destination}:{request.priority.value}"

    cached = _nav_cache.get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="application/json")

    logger.info(
        "Navigation: Computing path for user %s (%s -> %s) [%s]",
        request.user_id,
        request.current_zone,
        request.destination,
        request.priority,
    )

    source = _resolve_zone_id(request.current_zone)
    dest = _resolve_zone_id(request.destination)
    now = datetime.now()

    density_map, predictions = _fetch_crowd_data(now, request.event_phase.value)
    zone_scores = score_all_zones(
        density_map, predictions, event_phase=request.event_phase.value
    )

    # Core pathfinding execution
    route = find_best_route(
        source,
        dest,
        zone_scores,
        predictions=predictions,
        constraints=request.constraints,
        priority=request.priority,
    )

    if not route:
        logger.warning("Unreachable path request: %s -> %s", source, dest)
        raise HTTPException(
            status_code=422,
            detail=f"No navigable path currently found from '{source}' to '{dest}'.",
        )

    wait_minutes = estimate_wait_minutes(route, density_map)

    # Generate LLM grounding context
    prompt = build_navigation_prompt(
        current_zone=source,
        destination=dest,
        recommended_route=route,
        zone_scores=zone_scores,
        density_map=density_map,
        predictions=predictions,
        estimated_wait_minutes=wait_minutes,
        event_phase=request.event_phase.value,
        priority=request.priority.value,
    )
    explanation = get_ai_explanation(prompt)

    # Persist session in the background
    background_tasks.add_task(
        firestore_client.save_navigation_request,
        user_id=request.user_id,
        data={
            "source": source,
            "destination": dest,
            "route": route,
            "priority": request.priority.value,
            "constraints": request.constraints or [],
            "event_phase": request.event_phase.value,
            "wait_minutes": wait_minutes,
            "timestamp": now.isoformat(),
            "current_zone_index": 0,
            "dismissed_fingerprint": "",
            "dismissed_at": "",
        },
    )

    logger.info("Navigation optimized: %s -> %s (%d nodes)", source, dest, len(route))

    response_obj = _build_navigation_response(
        user_id=request.user_id,
        route=route,
        wait_minutes=wait_minutes,
        zone_scores=zone_scores,
        explanation=explanation,
    )

    # 7. Populate Barrier Cache
    _nav_cache.set(cache_key, response_obj.model_dump_json())

    return response_obj


@router.get("/alerts/{user_id}", response_model=RerouteAlertResponse)
def get_live_alerts(
    user_id: str,
    raw_request: Request,
    _rate: None = Depends(navigation_rate_limit),
) -> RerouteAlertResponse:
    """Monitors the user's active path for time-saving optimization gaps.

    If a newly computed path is >= 2 minutes faster than the current remaining
    path, a proactive reroute alert is generated. Suggestions that were
    previously dismissed are suppressed for 5 minutes.
    """
    user_state = firestore_client.get_user_history(user_id)
    if not user_state:
        return RerouteAlertResponse(requires_reroute=False)

    old_route = user_state.get("route", [])
    if not old_route:
        return RerouteAlertResponse(requires_reroute=False)

    dest = user_state.get("destination", "")

    # Offset based on user's current progression node
    zone_index = int(user_state.get("current_zone_index", 0))
    zone_index = min(zone_index, len(old_route) - 1)
    current_zone = old_route[zone_index]

    if current_zone == dest:
        return RerouteAlertResponse(requires_reroute=False)

    now = datetime.now()
    event_phase = user_state.get("event_phase", EventPhase.live.value)
    density_map, predictions = _fetch_crowd_data(now, event_phase)
    zone_scores = score_all_zones(density_map, predictions, event_phase=event_phase)

    new_route = find_best_route(
        current_zone,
        dest,
        zone_scores,
        predictions=predictions,
        constraints=user_state.get("constraints", []),
        priority=user_state.get("priority", "fast_exit"),
    )

    if not new_route or new_route == old_route[zone_index:]:
        return RerouteAlertResponse(requires_reroute=False)

    old_wait = estimate_wait_minutes(old_route[zone_index:], density_map)
    new_wait = estimate_wait_minutes(new_route, density_map)

    # Threshold alert — only disrupt the user if the gain is significant
    if (old_wait - new_wait) < 2:
        return RerouteAlertResponse(requires_reroute=False)

    # Fingerprint check for dismissal cooldown
    new_fingerprint = "-".join(new_route)
    if user_state.get("dismissed_fingerprint") == new_fingerprint and user_state.get(
        "dismissed_at"
    ):
        try:
            dismissed_at = datetime.fromisoformat(user_state["dismissed_at"])
            if (now - dismissed_at) < timedelta(minutes=_REROUTE_COOLDOWN_MINUTES):
                return RerouteAlertResponse(requires_reroute=False)
        except (ValueError, TypeError):
            pass

    # Regenerate explanation for the new recommendation
    prompt = build_navigation_prompt(
        current_zone=current_zone,
        destination=dest,
        recommended_route=new_route,
        zone_scores=zone_scores,
        density_map=density_map,
        predictions=predictions,
        estimated_wait_minutes=new_wait,
        event_phase=event_phase,
        priority=user_state.get("priority", "fast_exit"),
    )
    explanation = get_ai_explanation(prompt)

    new_nav = _build_navigation_response(
        user_id=user_id,
        route=new_route,
        wait_minutes=new_wait,
        zone_scores=zone_scores,
        explanation=explanation,
    )
    return RerouteAlertResponse(requires_reroute=True, new_navigation=new_nav)


@router.post("/accept/{user_id}", status_code=200)
def accept_reroute(
    user_id: str,
    new_route: List[str] = Body(..., description="The sequence of zones accepted."),
    _rate: None = Depends(navigation_rate_limit),
) -> Dict[str, Any]:
    """Updates the primary navigation session with the newly accepted path."""
    user_state = firestore_client.get_user_history(user_id)
    if not user_state:
        raise HTTPException(status_code=404, detail="Active session not found.")

    updated = {**user_state, "route": new_route}
    firestore_client.update_accepted_route(user_id, updated)
    return {"status": "accepted", "new_route": new_route}


@router.post("/dismiss/{user_id}", status_code=200)
def dismiss_reroute(
    user_id: str,
    dismissed_route: List[str] = Body(..., description="The route zones to suppress."),
    _rate: None = Depends(navigation_rate_limit),
) -> Dict[str, Any]:
    """Records a dismissal to suppress redundant alerts for the cooldown window."""
    fingerprint = "-".join(dismissed_route)
    firestore_client.update_dismissed_route(
        user_id,
        dismissed_fingerprint=fingerprint,
        dismissed_at=datetime.now().isoformat(),
    )
    return {"status": "dismissed", "suppressed_for_minutes": _REROUTE_COOLDOWN_MINUTES}
