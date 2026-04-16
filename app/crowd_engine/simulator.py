"""
crowd_engine/simulator.py
--------------------------
Simulates crowd density for each zone.

Design:
  - Uses the current hour + a zone-specific seed for deterministic-but-realistic values.
  - Peak hours boost density. Time-of-day shapes the base curve.
  - No external dependencies — pure Python math.
  - Results are cached for 2 seconds (see cache.py) so burst-repeated calls
    within the same polling cycle (e.g. /crowd/status + /crowd/wait-times) share
    one computation rather than re-running identical math.
"""

import random
import math
from datetime import datetime
from typing import Dict

from app.config import ZONE_REGISTRY, PEAK_HOUR_WINDOWS, DENSITY_STATUS_MAP
from app.crowd_engine.cache import crowd_cache


def _is_peak_hour(hour: int) -> bool:
    """Returns True if the given hour falls inside a peak window."""
    return any(start <= hour < end for start, end in PEAK_HOUR_WINDOWS)


def _base_density(hour: int, zone_id: str, zone_seed: int, event_phase: str = "live") -> float:
    """
    Produces a base density (0–100) driven by time-of-day and event context.
    Uses a sine wave with modifiers for specific event phases (surges).
    """
    # Gentle sinusoidal curve peaking around 18:00
    time_factor = (math.sin((hour - 6) * math.pi / 12) + 1) / 2  # 0.0 – 1.0
    peak_boost = 25 if _is_peak_hour(hour) else 0

    # Surge Modifiers based on Event Phase
    surge_boost = 0
    zone_type = ZONE_REGISTRY.get(zone_id, {}).get("type", "unknown")
    
    if event_phase == "halftime" and zone_type == "amenity":
        surge_boost = 35  # Food court rush
    elif event_phase == "exit" and zone_type == "gate":
        surge_boost = 45  # Mass exit surge
    elif event_phase == "pre_game" and zone_type == "gate":
        surge_boost = 30  # Entry surge

    # Zone-specific jitter so zones aren't identical
    rng = random.Random(zone_seed + hour)
    jitter = rng.uniform(-5, 5)

    density = (time_factor * 55) + peak_boost + surge_boost + jitter
    return max(0.0, min(100.0, density))


def _density_to_status(density: int) -> str:
    """Maps a density integer to a human-readable status label."""
    for threshold, label in DENSITY_STATUS_MAP:
        if density >= threshold:
            return label
    return "LOW"


def get_zone_density_map(now: datetime | None = None, event_phase: str = "live") -> Dict[str, int]:
    """
    Returns {zone_id: density_percent} for every zone.
    Pass `now` explicitly for deterministic testing; defaults to current time.
    Supports surge scenarios via `event_phase`.

    Results are cached at 2-second granularity (keyed on the integer second and phase).
    """
    resolved = now or datetime.now()
    use_cache = now is None 

    if use_cache:
        cache_key = ("density_map", int(resolved.timestamp()), event_phase)
        cached = crowd_cache.get(cache_key)
        if cached is not None:
            return cached

    result = {
        zone_id: int(_base_density(resolved.hour, zone_id, hash(zone_id) % 100, event_phase))
        for zone_id in ZONE_REGISTRY
    }

    if use_cache:
        crowd_cache.set(cache_key, result)

    return result


def get_zone_crowd_detail(zone_id: str, density_map: Dict[str, int]) -> Dict:
    """
    Returns a fully enriched dict for one zone, ready for the API response.
    Raises KeyError if the zone_id is unknown.
    """
    zone = ZONE_REGISTRY[zone_id]   # raises KeyError for unknown zones
    density = density_map[zone_id]
    return {
        "zone_id": zone_id,
        "name": zone["name"],
        "density": density,
        "status": _density_to_status(density),
    }
