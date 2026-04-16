"""
api/routes_navigation.py
-------------------------
Core navigation endpoint — orchestrates all engines for a complete suggestion.

Data flow inside this handler:
  1. Simulate current crowd → density_map
  2. Predict future crowd   → predictions
  3. Score all zones        → zone_scores
  4. Find best route        → route
  5. Estimate wait time     → wait_minutes
  6. Build Gemini prompt    → prompt
  7. Get AI explanation     → explanation
  8. Persist request        → Firestore (mock)
  9. Return NavigationResponse
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.crowd_engine.simulator import get_zone_density_map
from app.crowd_engine.predictor import predict_all_zones
from app.decision_engine.scorer import score_all_zones
from app.decision_engine.router import find_best_route, estimate_wait_minutes
from app.ai_engine.prompt_builder import build_navigation_prompt
from app.ai_engine.explainer import get_ai_explanation
from app.google_services import firestore_client, bigquery_client
from app.google_services.maps_client import get_walking_distance_meters, get_zone_coordinates
from app.middleware.rate_limiter import navigation_rate_limit
from app.models.navigation_models import NavigationRequest, NavigationResponse, ReasoningSummary, RerouteAlertResponse, Waypoint
from app.models.crowd_models import EventPhase
from app.config import ZONE_REGISTRY

# Cooldown period: the same dismissed reroute suggestion is suppressed for this duration.
_REROUTE_COOLDOWN_MINUTES = 5

router = APIRouter(prefix="/navigate", tags=["Navigation"])


def _resolve_zone_id(raw: str) -> str:
    """
    Accepts a zone_id (e.g. 'FC') or a zone name (e.g. 'Food Court')
    and returns the canonical zone_id.  Raises HTTPException if not found.
    """
    # Direct ID match
    if raw in ZONE_REGISTRY:
        return raw
    # Name-based match (case-insensitive)
    for zone_id, meta in ZONE_REGISTRY.items():
        if meta["name"].lower() == raw.lower():
            return zone_id
    raise HTTPException(
        status_code=404,
        detail=f"Zone '{raw}' not found. Valid IDs: {list(ZONE_REGISTRY.keys())}",
    )


def _fetch_crowd_data(now: datetime, event_phase: str) -> Tuple[Dict[str, int], Dict[str, Dict]]:
    """Retrieves current density and generates predictions for all zones.

    get_zone_density_map is called without an explicit `now` so it hits the
    2-second shared cache.  The resolved `now` is still forwarded to
    predict_all_zones to keep intra-request time references consistent.
    The density_map is passed in so predict_all_zones never calls
    get_zone_density_map a second time.
    """
    density_map = get_zone_density_map()   # cache-eligible — no explicit `now`
    _ = bigquery_client.query_peak_zones(top_n=3)  # warm BigQuery; activates live client when enabled
    predictions = predict_all_zones(now, event_phase=event_phase, density_map=density_map)
    return density_map, predictions



def _build_navigation_response(
    user_id: str,
    route: List[str],
    wait_minutes: int,
    zone_scores: Dict[str, Dict[str, int]],
    explanation: str
) -> NavigationResponse:
    """Constructs the standard structured NavigationResponse."""
    reasoning_summary = ReasoningSummary(
        density_factor=0.6,
        trend_factor=0.3,
        event_factor=0.1
    )
    
    # Calculate mapping overlays
    total_distance = 0
    waypoints = []
    
    if route:
        for i in range(len(route) - 1):
            total_distance += get_walking_distance_meters(route[i], route[i+1])
            
        for z in route:
            coords = get_zone_coordinates(z)
            if coords:
                waypoints.append(Waypoint(zone_id=z, lat=coords["lat"], lng=coords["lng"]))

    return NavigationResponse(
        user_id=user_id,
        recommended_route=route,
        estimated_wait_minutes=wait_minutes,
        total_walking_distance_meters=total_distance,
        route_waypoints=waypoints,
        zone_scores=zone_scores,
        reasoning_summary=reasoning_summary,
        ai_explanation=explanation,
    )


@router.post("/suggest", response_model=NavigationResponse)
def suggest_navigation(
    request: NavigationRequest,
    _rate: None = Depends(navigation_rate_limit),
):
    """
    Core endpoint: returns the recommended route + AI explanation.
    """
    source = _resolve_zone_id(request.current_zone)
    dest = _resolve_zone_id(request.destination)
    now = datetime.now()

    density_map, predictions = _fetch_crowd_data(now, request.event_phase.value)
    zone_scores = score_all_zones(density_map, predictions, event_phase=request.event_phase.value)

    route = find_best_route(source, dest, zone_scores, predictions=predictions, constraints=request.constraints, priority=request.priority)
    if not route:
        raise HTTPException(
            status_code=422,
            detail=f"No navigable path found from '{source}' to '{dest}'.",
        )

    wait_minutes = estimate_wait_minutes(route, density_map)

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

    firestore_client.save_navigation_request(
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
            # Trip-state fields used by the alerts endpoint
            "current_zone_index": 0,
            "dismissed_fingerprint": "",
            "dismissed_at": "",
        },
    )

    return _build_navigation_response(
        user_id=request.user_id,
        route=route,
        wait_minutes=wait_minutes,
        zone_scores=zone_scores,
        explanation=explanation
    )

@router.get("/alerts/{user_id}", response_model=RerouteAlertResponse)
def get_live_alerts(
    user_id: str,
    raw_request: Request,
    _rate: None = Depends(navigation_rate_limit),
):
    """
    Checks whether the user's active route has been superseded by a faster option.

    Uses the stored current_zone_index to route from the user's current position,
    not from the original source.  Suppresses identical reroute suggestions for
    _REROUTE_COOLDOWN_MINUTES after the user has dismissed them.
    """
    user_state = firestore_client.get_user_history(user_id)
    if not user_state:
        return RerouteAlertResponse(requires_reroute=False)

    old_route = user_state.get("route", [])
    if not old_route:
        return RerouteAlertResponse(requires_reroute=False)

    dest = user_state.get("destination", "")

    # Determine the user's current position within the route
    zone_index = int(user_state.get("current_zone_index", 0))
    zone_index = min(zone_index, len(old_route) - 1)
    current_zone = old_route[zone_index]

    # Already at the destination
    if current_zone == dest:
        return RerouteAlertResponse(requires_reroute=False)

    now = datetime.now()
    event_phase = user_state.get("event_phase", EventPhase.live.value)
    density_map, predictions = _fetch_crowd_data(now, event_phase)
    zone_scores = score_all_zones(density_map, predictions, event_phase=event_phase)

    new_route = find_best_route(
        current_zone, dest, zone_scores,
        predictions=predictions,
        constraints=user_state.get("constraints", []),
        priority=user_state.get("priority", "fast_exit")
    )

    if not new_route or new_route == old_route[zone_index:]:
        return RerouteAlertResponse(requires_reroute=False)

    old_wait = estimate_wait_minutes(old_route[zone_index:], density_map)
    new_wait = estimate_wait_minutes(new_route, density_map)

    # Only alert if the new route meaningfully saves time (>= 2 minutes)
    if (old_wait - new_wait) < 2:
        return RerouteAlertResponse(requires_reroute=False)

    # ── Cooldown check ──────────────────────────────────────────────────────
    new_fingerprint = "-".join(new_route)
    dismissed_fp = user_state.get("dismissed_fingerprint", "")
    dismissed_at_str = user_state.get("dismissed_at", "")

    if dismissed_fp and dismissed_fp == new_fingerprint and dismissed_at_str:
        try:
            dismissed_at = datetime.fromisoformat(dismissed_at_str)
            if (now - dismissed_at) < timedelta(minutes=_REROUTE_COOLDOWN_MINUTES):
                # Same alert dismissed recently — suppress
                return RerouteAlertResponse(requires_reroute=False)
        except ValueError:
            pass  # malformed timestamp — proceed normally

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
        explanation=explanation
    )
    return RerouteAlertResponse(requires_reroute=True, new_navigation=new_nav)


@router.post("/accept/{user_id}", status_code=200)
def accept_reroute(
    user_id: str,
    new_route: List[str] = Body(..., description="The new route the user accepted."),
    _rate: None = Depends(navigation_rate_limit),
):
    """
    Persists an accepted reroute as the user's active navigation state.

    Resets dismissed-alert state so the reroute cannot repeat immediately.
    """
    user_state = firestore_client.get_user_history(user_id)
    if not user_state:
        raise HTTPException(status_code=404, detail="No active navigation session found for this user.")

    updated = {**user_state, "route": new_route}
    firestore_client.update_accepted_route(user_id, updated)
    return {"status": "accepted", "new_route": new_route}


@router.post("/dismiss/{user_id}", status_code=200)
def dismiss_reroute(
    user_id: str,
    dismissed_route: List[str] = Body(..., description="The reroute suggestion the user dismissed."),
    _rate: None = Depends(navigation_rate_limit),
):
    """
    Records a dismissed reroute fingerprint.

    Prevents the same suggestion from reappearing for _REROUTE_COOLDOWN_MINUTES.
    """
    fingerprint = "-".join(dismissed_route)
    firestore_client.update_dismissed_route(
        user_id,
        dismissed_fingerprint=fingerprint,
        dismissed_at=datetime.now().isoformat(),
    )
    return {"status": "dismissed", "suppressed_for_minutes": _REROUTE_COOLDOWN_MINUTES}
