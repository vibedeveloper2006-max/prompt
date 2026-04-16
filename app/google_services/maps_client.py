"""
google_services/maps_client.py
--------------------------------
Google Maps Platform integration.

Provides real-world walking distances and venue coordinates using the
Google Maps SDK. Falls back to deterministic mock data if the API is
unavailable or the key is not configured.
"""

import logging
from typing import Dict, Optional
import googlemaps
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Setup Maps Client
# ---------------------------------------------------------------------------
_gmaps = None
if settings.maps_enabled and settings.maps_api_key:
    try:
        _gmaps = googlemaps.Client(key=settings.maps_api_key)
        logger.info("Google Maps client initialized.")
    except Exception as e:
        logger.warning(f"Failed to initialize Google Maps client: {e}")

# ---------------------------------------------------------------------------
# Fallback Mock Data
# ---------------------------------------------------------------------------
_MOCK_DISTANCES: Dict[str, int] = {
    "A-Corridor_1": 80, "A-Corridor_2": 120, "B-Corridor_1": 90,
    "B-Corridor_3": 100, "C-Corridor_2": 110, "C-Corridor_3": 95,
    "FC-Corridor_1": 70, "FC-Corridor_2": 85, "ST-Corridor_2": 150,
    "ST-Corridor_3": 130, "Corridor_3-RR_1": 40,
}

_MOCK_COORDS: Dict[str, Dict[str, float]] = {
    "A": {"lat": 12.9716, "lng": 77.5946}, "B": {"lat": 12.9720, "lng": 77.5950},
    "C": {"lat": 12.9710, "lng": 77.5960}, "FC": {"lat": 12.9714, "lng": 77.5955},
    "ST": {"lat": 12.9718, "lng": 77.5965}, "Corridor_1": {"lat": 12.9717, "lng": 77.5948},
    "Corridor_2": {"lat": 12.9715, "lng": 77.5958}, "Corridor_3": {"lat": 12.9719, "lng": 77.5957},
    "RR_1": {"lat": 12.9721, "lng": 77.5959},
}


def get_walking_distance_meters(zone_a: str, zone_b: str) -> int:
    """Returns real walking distance via Distance Matrix API with mock fallback."""
    if _gmaps:
        try:
            # Get coordinates for origin and destination
            origin = get_zone_coordinates(zone_a)
            dest = get_zone_coordinates(zone_b)
            
            if origin and dest:
                result = _gmaps.distance_matrix(
                    origins=[(origin["lat"], origin["lng"])],
                    destinations=[(dest["lat"], dest["lng"])],
                    mode="walking"
                )
                
                element = result["rows"][0]["elements"][0]
                if element["status"] == "OK":
                    distance = element["distance"]["value"]
                    logger.debug("Maps [LIVE] distance %s → %s = %d m", zone_a, zone_b, distance)
                    return distance
        except Exception as e:
            logger.error(f"Google Maps Distance Matrix error: {e}. Falling back to mock.")

    # Mock Fallback
    key1 = f"{zone_a}-{zone_b}"
    key2 = f"{zone_b}-{zone_a}"
    distance = _MOCK_DISTANCES.get(key1) or _MOCK_DISTANCES.get(key2) or 100
    logger.debug("Maps [FALLBACK] distance %s → %s = %d m", zone_a, zone_b, distance)
    return distance


def get_zone_coordinates(zone_id: str) -> Optional[Dict[str, float]]:
    """Returns GPS coordinates for a zone. (Mock used as primary coordinate registry)."""
    # Note: In a real deployment, we might lookup a Places ID, 
    # but for stadium zones, we use the internal coordinate registry.
    coords = _MOCK_COORDS.get(zone_id)
    if coords is None:
        logger.warning("Maps: no coordinates for zone '%s'", zone_id)
    return coords
