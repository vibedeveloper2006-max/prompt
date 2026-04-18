"""
decision_engine/scorer.py
--------------------------
Scores each zone on a 0–100 scale (higher = better to visit).

Score formula:
  base_score = 100 - current_density   (less crowd = higher base)
  trend_bonus = +10 if DECREASING else -10 if INCREASING else 0
  capacity_factor = zone_capacity / 500 (larger venues handle crowds better)
  final = clamp(base_score + trend_bonus + capacity_factor_adjustment, 0, 100)
"""

from typing import Dict

from app.config import ZONE_REGISTRY


def _calculate_trend_adjustment(trend: str) -> int:
    """Calculates modifier based on future predicted crowd trend."""
    return {"DECREASING": +10, "STABLE": 0, "INCREASING": -10}.get(trend, 0)


def _calculate_capacity_adjustment(zone_id: str) -> int:
    """Larger venues handle crowds better."""
    capacity = ZONE_REGISTRY.get(zone_id, {}).get("capacity", 300)
    return min(10, (capacity - 200) // 50)


def _calculate_phase_adjustment(zone_id: str, event_phase: str) -> int:
    """Penalize routing to areas expected to be packed for specific phases."""
    ztype = ZONE_REGISTRY.get(zone_id, {}).get("type", "unknown")
    if event_phase == "halftime" and ztype == "amenity":
        return -10
    if event_phase == "exit" and ztype == "gate":
        return -10
    return 0


def _calculate_confidence(score: int, trend: str) -> int:
    """Adjusts AI confidence based on directionality of the crowd."""
    if trend == "INCREASING":
        conf_raw = score - 5
    elif trend == "DECREASING":
        conf_raw = score + 5
    else:
        conf_raw = score
    return max(0, min(100, conf_raw))


def score_zone(
    zone_id: str,
    current_density: int,
    trend: str,
    event_phase: str = "live",
) -> Dict[str, int]:
    """
    Returns a dictionary with score (0–100) and confidence_score (0-100) for a zone.
    Higher score → better choice for the user right now.

    Args:
        zone_id:         Zone identifier (must exist in ZONE_REGISTRY).
        current_density: Current crowd percentage (0–100).
        trend:           One of INCREASING | STABLE | DECREASING.
    """
    base_score = 100 - current_density

    raw = (
        base_score
        + _calculate_trend_adjustment(trend)
        + _calculate_capacity_adjustment(zone_id)
        + _calculate_phase_adjustment(zone_id, event_phase)
    )
    score = max(0, min(100, raw))

    return {"score": score, "confidence_score": _calculate_confidence(score, trend)}


def score_all_zones(
    density_map: Dict[str, int],
    predictions: Dict[str, Dict],
    event_phase: str = "live",
) -> Dict[str, Dict[str, int]]:
    """
    Returns {zone_id: {"score": int, "confidence_score": int}} for all zones.

    Args:
        density_map:  {zone_id: current_density} from simulator.
        predictions:  {zone_id: prediction_dict} from predictor.
        event_phase:  Current event phase.
    """
    return {
        zone_id: score_zone(
            zone_id,
            density_map[zone_id],
            predictions[zone_id]["trend"],
            event_phase,
        )
        for zone_id in density_map
    }
