"""
tests/test_integration.py
--------------------------
Integration-style tests that verify cross-feature contracts and end-to-end
attendee / staff flows without requiring external services.

These tests ensure:
  1. A full attendee round-trip produces correct, schema-valid output.
  2. Analytics and navigation responses share consistent zone identifiers.
  3. Gemini / BigQuery fallbacks return gracefully when credentials are absent.
  4. API response schemas remain stable (contract/regression tests).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.analytics_models import AnalyticsResponse

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

_NAV_PAYLOAD = {
    "user_id": "integration-user-1",
    "current_zone": "A",
    "destination": "ST",
    "priority": "fast_exit",
}

_NAV_HEADERS = {"X-Forwarded-For": "10.200.0.1"}  # dedicated IP bucket for integration tests

_CHAT_PAYLOAD = {
    "user_id": "integration-user-1",
    "message": "What items are prohibited at the venue?",
}


# ---------------------------------------------------------------------------
# 1. Full attendee flow
# ---------------------------------------------------------------------------

class TestFullAttendeeFlow:
    """Simulates a complete attendee session: zone lookup → route → insights."""

    def test_zones_available(self):
        """Crowd status must return at least one zone."""
        resp = client.get("/crowd/status")
        assert resp.status_code == 200
        zones = resp.json()["zones"]
        assert len(zones) >= 1

    def test_route_returns_valid_schema(self):
        resp = client.post("/navigate/suggest", json=_NAV_PAYLOAD, headers=_NAV_HEADERS)
        assert resp.status_code == 200
        data = resp.json()

        required_keys = {
            "user_id", "recommended_route", "estimated_wait_minutes",
            "zone_scores", "reasoning_summary", "ai_explanation",
        }
        assert required_keys.issubset(data.keys())

    def test_route_contains_source_and_dest(self):
        resp = client.post("/navigate/suggest", json=_NAV_PAYLOAD, headers=_NAV_HEADERS)
        assert resp.status_code == 200
        route = resp.json()["recommended_route"]
        assert route[0] == "A"
        assert route[-1] == "ST"

    def test_route_includes_waypoints(self):
        """Waypoints must be present and have lat/lng when coordinates are mocked."""
        resp = client.post("/navigate/suggest", json=_NAV_PAYLOAD, headers=_NAV_HEADERS)
        assert resp.status_code == 200
        waypoints = resp.json().get("route_waypoints", [])
        if waypoints:  # Mocks may return empty list; if present, validate shape
            for wp in waypoints:
                assert "zone_id" in wp
                assert "lat" in wp
                assert "lng" in wp

    def test_insights_endpoint_returns_data(self):
        resp = client.get("/analytics/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert "historical_hotspots" in data
        assert "live_leaderboard" in data
        assert "recommended_entry" in data

    def test_zone_ids_consistent_across_endpoints(self):
        """Zone IDs from /crowd/status must be a superset of the route returned."""
        zones_resp = client.get("/crowd/status")
        zone_ids = {z["zone_id"] for z in zones_resp.json()["zones"]}

        nav_resp = client.post("/navigate/suggest", json=_NAV_PAYLOAD, headers=_NAV_HEADERS)
        assert nav_resp.status_code == 200
        route = nav_resp.json()["recommended_route"]

        for z in route:
            assert z in zone_ids, f"Route zone '{z}' not present in /crowd/status"

    def test_wait_times_available(self):
        resp = client.get("/crowd/wait-times")
        assert resp.status_code == 200
        services = resp.json()["services"]
        assert len(services) >= 1

    def test_chat_returns_reply(self):
        resp = client.post("/assistant/chat", json=_CHAT_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert isinstance(data["reply"], str)
        assert len(data["reply"]) > 0


# ---------------------------------------------------------------------------
# 2. Fallback resilience
# ---------------------------------------------------------------------------

class TestFallbackResilience:
    """Verifies that missing credentials / unavailable services degrade gracefully."""

    def test_assistant_fallback_when_no_api_key(self):
        """With no Gemini key, chatbot must return a fallback string, not a 500."""
        # The test environment has no real GEMINI_API_KEY set, so this already
        # exercises the fallback path built in app/ai_engine/chatbot.py.
        resp = client.post("/assistant/chat", json=_CHAT_PAYLOAD)
        assert resp.status_code == 200
        assert "reply" in resp.json()
        # error flag may be True in fallback mode but the endpoint must still respond
        assert "error" in resp.json()

    def test_navigation_ai_fallback(self):
        """Navigation must succeed even if AI explanation is unavailable."""
        resp = client.post("/navigate/suggest", json=_NAV_PAYLOAD, headers=_NAV_HEADERS)
        assert resp.status_code == 200
        # ai_explanation can be None or a fallback string — both are acceptable
        data = resp.json()
        assert "recommended_route" in data
        assert isinstance(data["recommended_route"], list)

    def test_analytics_fallback_bigquery(self):
        """Analytics endpoint must still respond when BigQuery is unavailable."""
        resp = client.get("/analytics/insights")
        assert resp.status_code == 200
        # historical_hotspots may be empty if BQ is mocked, but list must be present
        assert isinstance(resp.json()["historical_hotspots"], list)

    def test_reroute_alert_for_unknown_user(self):
        """Alert endpoint must handle unknown user IDs without crashing."""
        resp = client.get("/navigate/alerts/unknown-ghost-user-9999", headers=_NAV_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["requires_reroute"] is False


# ---------------------------------------------------------------------------
# 3. API schema contract / regression tests
# ---------------------------------------------------------------------------

class TestSchemaContracts:
    """
    Asserts that response shapes remain stable so front-end JS and future
    integrations do not break silently after a backend refactor.
    """

    def test_health_schema(self):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data

    def test_crowd_status_zone_schema(self):
        zones = client.get("/crowd/status").json()["zones"]
        # capacity is not surfaced in the API response — only runtime fields are checked
        required = {"zone_id", "name", "density", "status"}
        for z in zones:
            assert required.issubset(z.keys()), f"Zone missing keys: {required - z.keys()}"

    def test_navigation_response_schema(self):
        resp = client.post("/navigate/suggest", json=_NAV_PAYLOAD, headers=_NAV_HEADERS)
        data = resp.json()
        top_level = {
            "user_id", "recommended_route", "estimated_wait_minutes",
            "total_walking_distance_meters", "route_waypoints",
            "zone_scores", "reasoning_summary",
        }
        assert top_level.issubset(data.keys())

    def test_reasoning_summary_schema(self):
        resp = client.post("/navigate/suggest", json=_NAV_PAYLOAD, headers=_NAV_HEADERS)
        rs = resp.json()["reasoning_summary"]
        assert "density_factor" in rs
        assert "trend_factor" in rs
        assert "event_factor" in rs
        # All factors must be floats in [0, 1]
        for key in ("density_factor", "trend_factor", "event_factor"):
            assert 0.0 <= rs[key] <= 1.0, f"{key} out of range: {rs[key]}"

    def test_analytics_response_schema(self):
        resp = client.get("/analytics/insights")
        data = resp.json()
        assert isinstance(data["historical_hotspots"], list)
        assert isinstance(data["live_leaderboard"], list)
        assert isinstance(data["recommended_entry"], str)

    def test_analytics_leaderboard_item_schema(self):
        leaderboard = client.get("/analytics/insights").json()["live_leaderboard"]
        if leaderboard:
            item = leaderboard[0]
            required = {"zone_id", "name", "current_density", "status"}
            assert required.issubset(item.keys())

    def test_wait_times_service_schema(self):
        services = client.get("/crowd/wait-times").json()["services"]
        required = {"name", "wait_minutes", "status", "trend"}
        for svc in services:
            assert required.issubset(svc.keys())

    def test_analytics_pydantic_model_matches_endpoint(self):
        """Pydantic model fields must exactly cover the endpoint output keys."""
        resp = client.get("/analytics/insights")
        endpoint_keys = set(resp.json().keys())
        model_keys = set(AnalyticsResponse.model_fields.keys())
        assert model_keys == endpoint_keys, (
            f"Schema drift detected!\n"
            f"  Model fields:    {sorted(model_keys)}\n"
            f"  Endpoint keys:   {sorted(endpoint_keys)}"
        )
