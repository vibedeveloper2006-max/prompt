"""
tests/test_analytics.py
------------------------
Expanded tests for the /analytics/insights endpoint and the AnalyticsResponse
Pydantic model. Covers schema validation, sort order, fallback behaviour,
leaderboard density correctness, recommended_entry logic, and cache isolation.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.analytics_models import AnalyticsResponse, LiveZoneStatus
from app.middleware.rate_limiter import analytics_rate_limit

client = TestClient(app)

# Dedicated IP so analytics tests never share a rate-limit bucket with other suites
_HEADERS = {"X-Forwarded-For": "10.210.0.1"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_insights():
    resp = client.get("/analytics/insights", headers=_HEADERS)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Basic schema
# ---------------------------------------------------------------------------

class TestAnalyticsSchema:
    def test_get_insights_returns_200(self):
        resp = client.get("/analytics/insights", headers=_HEADERS)
        assert resp.status_code == 200

    def test_has_historical_hotspots(self):
        data = _get_insights()
        assert "historical_hotspots" in data
        assert isinstance(data["historical_hotspots"], list)

    def test_has_live_leaderboard(self):
        data = _get_insights()
        assert "live_leaderboard" in data
        assert isinstance(data["live_leaderboard"], list)

    def test_has_recommended_entry(self):
        data = _get_insights()
        assert "recommended_entry" in data
        assert isinstance(data["recommended_entry"], str)

    def test_response_has_exactly_three_keys(self):
        """Schema must have exactly the three documented keys — no silent additions."""
        data = _get_insights()
        assert set(data.keys()) == {"historical_hotspots", "live_leaderboard", "recommended_entry"}

    def test_leaderboard_not_empty(self):
        """Live leaderboard must contain at least one entry (all zones are always present)."""
        data = _get_insights()
        assert len(data["live_leaderboard"]) > 0

    def test_recommended_entry_not_blank(self):
        """recommended_entry must never be an empty string."""
        data = _get_insights()
        assert data["recommended_entry"] != ""


# ---------------------------------------------------------------------------
# 2. Leaderboard item schema
# ---------------------------------------------------------------------------

class TestLeaderboardItemSchema:
    def test_leaderboard_item_has_zone_id(self):
        item = _get_insights()["live_leaderboard"][0]
        assert "zone_id" in item

    def test_leaderboard_item_has_name(self):
        item = _get_insights()["live_leaderboard"][0]
        assert "name" in item
        assert isinstance(item["name"], str)
        assert len(item["name"]) > 0

    def test_leaderboard_item_has_current_density(self):
        item = _get_insights()["live_leaderboard"][0]
        assert "current_density" in item
        assert isinstance(item["current_density"], int)

    def test_leaderboard_item_density_in_valid_range(self):
        for item in _get_insights()["live_leaderboard"]:
            assert 0 <= item["current_density"] <= 100, (
                f"Zone {item['zone_id']} density out of range: {item['current_density']}"
            )

    def test_leaderboard_item_has_status(self):
        item = _get_insights()["live_leaderboard"][0]
        assert "status" in item
        assert item["status"] in ("LOW", "MEDIUM", "HIGH")

    def test_leaderboard_sorted_descending_by_density(self):
        """Leaderboard must be sorted highest-density first."""
        leaderboard = _get_insights()["live_leaderboard"]
        densities = [item["current_density"] for item in leaderboard]
        assert densities == sorted(densities, reverse=True), (
            "Leaderboard is not sorted descending by current_density"
        )


# ---------------------------------------------------------------------------
# 3. Recommended entry logic
# ---------------------------------------------------------------------------

class TestRecommendedEntry:
    def test_recommended_entry_is_a_gate(self):
        """recommended_entry must resolve to a gate-type zone name."""
        from app.config import ZONE_REGISTRY
        gate_names = {
            meta["name"] for meta in ZONE_REGISTRY.values()
            if meta.get("type") == "gate"
        }
        data = _get_insights()
        # N/A is the only valid non-gate fallback
        if data["recommended_entry"] != "N/A":
            assert data["recommended_entry"] in gate_names, (
                f"Unexpected recommended_entry: {data['recommended_entry']!r}. "
                f"Valid gate names: {gate_names}"
            )

    def test_recommended_entry_matches_leaderboard_zone(self):
        """recommended_entry must appear in the live_leaderboard zone names."""
        data = _get_insights()
        entry = data["recommended_entry"]
        if entry == "N/A":
            return
        leaderboard_names = {item["name"] for item in data["live_leaderboard"]}
        assert entry in leaderboard_names


# ---------------------------------------------------------------------------
# 4. Pydantic model
# ---------------------------------------------------------------------------

class TestAnalyticsModel:
    def test_model_serialization(self):
        resp = AnalyticsResponse(
            historical_hotspots=["Food Court", "Main Gate"],
            live_leaderboard=[],
            recommended_entry="Gate A",
        )
        dumped = resp.model_dump()
        assert dumped["historical_hotspots"] == ["Food Court", "Main Gate"]
        assert dumped["recommended_entry"] == "Gate A"
        assert dumped["live_leaderboard"] == []

    def test_model_fields_match_endpoint_keys(self):
        """Pydantic model fields must exactly cover the endpoint output keys."""
        resp = client.get("/analytics/insights", headers=_HEADERS)
        endpoint_keys = set(resp.json().keys())
        model_keys = set(AnalyticsResponse.model_fields.keys())
        assert model_keys == endpoint_keys, (
            f"Schema drift! Model: {sorted(model_keys)}, Endpoint: {sorted(endpoint_keys)}"
        )

    def test_live_zone_status_model_valid(self):
        zone = LiveZoneStatus(
            zone_id="A",
            name="Gate A",
            current_density=45,
            status="MEDIUM",
        )
        dumped = zone.model_dump()
        assert dumped["zone_id"] == "A"
        assert dumped["status"] == "MEDIUM"


# ---------------------------------------------------------------------------
# 5. Fallback resilience
# ---------------------------------------------------------------------------

class TestAnalyticsFallback:
    def test_bigquery_absent_returns_empty_hotspots(self):
        """With BQ mocked/absent, historical_hotspots may be empty but must be a list."""
        data = _get_insights()
        assert isinstance(data["historical_hotspots"], list)

    def test_endpoint_never_returns_500(self):
        resp = client.get("/analytics/insights", headers={"X-Forwarded-For": "10.211.0.1"})
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# 6. Rate limiting
# ---------------------------------------------------------------------------

class TestAnalyticsRateLimit:
    def test_analytics_rate_limit_triggers(self):
        """Analytics endpoint should 429 after 30 req/min."""
        analytics_rate_limit.store.clear()
        headers = {"X-Forwarded-For": "192.168.210.10"}
        hit_429 = False
        for _ in range(32):
            resp = client.get("/analytics/insights", headers=headers)
            if resp.status_code == 429:
                hit_429 = True
                break
        assert hit_429, "Expected HTTP 429 after exceeding analytics rate limit"

    def test_analytics_429_has_retry_after(self):
        analytics_rate_limit.store.clear()
        headers = {"X-Forwarded-For": "192.168.211.10"}
        for _ in range(32):
            resp = client.get("/analytics/insights", headers=headers)
            if resp.status_code == 429:
                assert "retry-after" in resp.headers
                return
        pytest.fail("Rate limit was never triggered")
