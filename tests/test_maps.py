"""
test_maps.py
------------
Tests the venue maps integration and coordinate/distance coverage.
"""

from fastapi.testclient import TestClient
from app.main import app
from app.google_services.maps_client import (
    get_zone_coordinates,
    get_walking_distance_meters,
)
from app.config import ZONE_REGISTRY

client = TestClient(app)

# Dedicated IP bucket so this test never trips the shared navigation rate limit
_HEADERS = {"X-Forwarded-For": "10.202.0.1"}


def test_venue_maps_response():
    """Navigation suggest returns all waypoints with positive coordinates."""
    payload = {
        "user_id": "test-map-user",
        "current_zone": "A",
        "destination": "ST",
        "priority": "fast_exit",
        "constraints": [],
    }

    response = client.post("/navigate/suggest", json=payload, headers=_HEADERS)
    assert response.status_code == 200

    data = response.json()
    assert "total_walking_distance_meters" in data
    assert "route_waypoints" in data

    assert data["total_walking_distance_meters"] > 0
    assert len(data["route_waypoints"]) > 0

    route = data["recommended_route"]
    assert len(data["route_waypoints"]) == len(route)

    wp0 = data["route_waypoints"][0]
    assert wp0["zone_id"] == route[0]
    assert wp0["lat"] > 0
    assert wp0["lng"] > 0


class TestZoneCoordinateCoverage:
    """Every zone in ZONE_REGISTRY must have GPS coordinates."""

    def test_all_registry_zones_have_coordinates(self):
        missing = [zone for zone in ZONE_REGISTRY if get_zone_coordinates(zone) is None]
        assert missing == [], f"Missing map coordinates for zones: {missing}"

    def test_rr1_coordinate_present(self):
        """RR_1 (Main Restroom) was previously missing — ensure it is now covered."""
        coords = get_zone_coordinates("RR_1")
        assert coords is not None, "RR_1 must have map coordinates"
        assert isinstance(coords["lat"], float)
        assert isinstance(coords["lng"], float)
        assert coords["lat"] > 0
        assert coords["lng"] > 0

    def test_unknown_zone_returns_none(self):
        """Non-existent zones return None without raising."""
        coords = get_zone_coordinates("NONEXISTENT_XYZ")
        assert coords is None


class TestWalkingDistanceFallback:
    """Distance lookup falls back to 100 m gracefully for unknown edges."""

    def test_known_edge_a_to_corridor1(self):
        d = get_walking_distance_meters("A", "Corridor_1")
        assert d == 80

    def test_known_edge_corridor3_to_rr1(self):
        d = get_walking_distance_meters("Corridor_3", "RR_1")
        assert d == 40

    def test_unknown_edge_falls_back_to_100(self):
        d = get_walking_distance_meters("A", "UNKNOWN_ZONE")
        assert d == 100
