"""
tests/test_api.py
------------------
Integration tests for all API endpoints using FastAPI's TestClient.
These do NOT call real Gemini or Google services (mocks are used automatically).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Dedicated IP buckets per test class to avoid cross-test rate-limit interference
_NAV_HEADERS = {"X-Forwarded-For": "10.203.0.1"}


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_returns_version(self):
        resp = client.get("/health")
        assert "version" in resp.json()


class TestCrowdEndpoints:
    def test_crowd_status_returns_all_zones(self):
        resp = client.get("/crowd/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "zones" in data
        assert len(data["zones"]) > 0

    def test_crowd_status_zone_structure(self):
        resp = client.get("/crowd/status")
        zone = resp.json()["zones"][0]
        assert "zone_id" in zone
        assert "density" in zone
        assert "status" in zone
        assert zone["status"] in ("LOW", "MEDIUM", "HIGH")

    def test_crowd_predict_valid_zone(self):
        resp = client.get("/crowd/predict?zone_id=A")
        assert resp.status_code == 200
        data = resp.json()
        assert data["zone_id"] == "A"
        assert "predicted_density" in data
        assert "trend" in data

    def test_crowd_predict_invalid_zone(self):
        resp = client.get("/crowd/predict?zone_id=INVALID")
        assert resp.status_code == 404

    def test_crowd_predict_food_court(self):
        resp = client.get("/crowd/predict?zone_id=FC")
        assert resp.status_code == 200


class TestNavigationEndpoint:
    def _suggest(self, current: str, dest: str, priority: str = "fastest"):
        return client.post("/navigate/suggest", json={
            "user_id": "test_user",
            "current_zone": current,
            "destination": dest,
            "priority": priority,
        }, headers=_NAV_HEADERS)

    def test_suggest_returns_route(self):
        resp = self._suggest("A", "FC")
        assert resp.status_code == 200
        data = resp.json()
        assert "recommended_route" in data
        assert len(data["recommended_route"]) > 0

    def test_suggest_route_starts_at_source(self):
        resp = self._suggest("A", "FC")
        assert resp.json()["recommended_route"][0] == "A"

    def test_suggest_route_ends_at_destination(self):
        resp = self._suggest("A", "ST")
        assert resp.json()["recommended_route"][-1] == "ST"

    def test_suggest_contains_zone_scores(self):
        resp = self._suggest("B", "FC")
        assert "zone_scores" in resp.json()

    def test_suggest_contains_ai_explanation(self):
        resp = self._suggest("A", "FC")
        data = resp.json()
        assert "ai_explanation" in data
        assert isinstance(data["ai_explanation"], str)
        assert len(data["ai_explanation"]) > 10

    def test_suggest_invalid_source_zone(self):
        resp = self._suggest("INVALID", "FC")
        assert resp.status_code == 404

    def test_suggest_invalid_destination_zone(self):
        resp = self._suggest("A", "NOWHERE")
        assert resp.status_code == 404

    def test_suggest_accepts_zone_names(self):
        # Test that zone names work as well as zone IDs
        resp = self._suggest("Gate A", "Food Court")
        assert resp.status_code == 200

    def test_suggest_same_source_destination(self):
        resp = self._suggest("A", "A")
        assert resp.status_code == 200
        assert resp.json()["recommended_route"] == ["A"]

    def test_suggest_end_to_end_payload(self):
        resp = client.post("/navigate/suggest", json={
            "user_id": "e2e_tester",
            "current_zone": "A",
            "destination": "FC",
            "priority": "fastest",
            "constraints": ["prefer_fastest"],
            "user_note": "I just want my hotdog"
        }, headers=_NAV_HEADERS)
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert "recommended_route" in data
        assert isinstance(data["recommended_route"], list)
        
        assert "ai_explanation" in data
        assert isinstance(data["ai_explanation"], str)
        
        assert "reasoning_summary" in data
        assert "density_factor" in data["reasoning_summary"]
        assert "trend_factor" in data["reasoning_summary"]
        assert "event_factor" in data["reasoning_summary"]
