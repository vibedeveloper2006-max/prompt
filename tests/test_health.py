"""
tests/test_health.py
---------------------
Tests for the /health endpoint — verifies schema, version, service status map,
and correct reporting of all Google / AI service integration readiness fields.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)


class TestHealthSchema:
    """Verifies the /health response shape and required fields."""

    def test_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status_ok(self):
        resp = client.get("/health")
        assert resp.json()["status"] == "ok"

    def test_health_has_correct_version(self):
        resp = client.get("/health")
        assert resp.json()["version"] == settings.app_version

    def test_health_version_is_1_2_0(self):
        """Verify version string matches the advertised v1.2.0."""
        resp = client.get("/health")
        assert resp.json()["version"] == "1.2.0"

    def test_health_has_app_name(self):
        resp = client.get("/health")
        assert "app_name" in resp.json()
        assert isinstance(resp.json()["app_name"], str)
        assert len(resp.json()["app_name"]) > 0

    def test_health_has_services_block(self):
        """Ensures the Google/AI service readiness map is present."""
        resp = client.get("/health")
        assert "services" in resp.json()

    def test_health_services_has_firestore(self):
        services = client.get("/health").json()["services"]
        assert "firestore" in services
        assert services["firestore"] in ("enabled", "disabled", "configured", "error")

    def test_health_services_has_bigquery(self):
        services = client.get("/health").json()["services"]
        assert "bigquery" in services
        assert services["bigquery"] in ("enabled", "disabled", "configured", "error")

    def test_health_services_has_maps(self):
        services = client.get("/health").json()["services"]
        assert "maps" in services
        assert services["maps"] in ("enabled", "disabled", "error")

    def test_health_services_has_gemini(self):
        services = client.get("/health").json()["services"]
        assert "gemini" in services
        assert services["gemini"] in ("enabled", "disabled", "configured", "error")

    def test_health_services_four_keys(self):
        """Exactly four integration services must be reported."""
        services = client.get("/health").json()["services"]
        expected = {"firestore", "bigquery", "maps", "gemini"}
        assert expected.issubset(services.keys())

    def test_health_no_creds_services_disabled(self):
        """In the test environment (no real GCP keys), services should be disabled/configured."""
        services = client.get("/health").json()["services"]
        # When FIRESTORE_ENABLED=false, firestore must be 'disabled'
        if not settings.firestore_enabled:
            assert services["firestore"] == "disabled"
        # When BIGQUERY_ENABLED=false, bigquery must be 'disabled'
        if not settings.bigquery_enabled:
            assert services["bigquery"] == "disabled"
        # When MAPS_ENABLED=false or no key, maps must be 'disabled'
        if not settings.maps_enabled or not settings.maps_api_key:
            assert services["maps"] == "disabled"
        # When GEMINI_API_KEY is absent, gemini must be 'disabled'
        if not settings.gemini_api_key:
            assert services["gemini"] == "disabled"


class TestHealthSecurityHeaders:
    """Verifies all required security headers are present on /health responses."""

    def _headers(self) -> dict:
        return client.get("/health").headers

    def test_x_content_type_options(self):
        assert self._headers().get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self):
        assert self._headers().get("x-frame-options") == "DENY"

    def test_referrer_policy(self):
        assert self._headers().get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_csp_present(self):
        assert "content-security-policy" in self._headers()

    def test_permissions_policy_present(self):
        pp = self._headers().get("permissions-policy", "")
        assert "camera=()" in pp

    def test_coop_header(self):
        coop = self._headers().get("cross-origin-opener-policy", "")
        assert coop == "same-origin"

    def test_corp_header(self):
        corp = self._headers().get("cross-origin-resource-policy", "")
        assert corp == "same-origin"
