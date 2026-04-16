"""
tests/test_performance.py
--------------------------
Smoke tests that assert critical endpoints respond within acceptable latency
bounds under the test environment's single-process execution.

Thresholds are deliberately generous (500 ms for navigation, 200 ms for
read-only endpoints) to avoid false flakes in CI while still catching
obvious regressions caused by blocking I/O or runaway loops.

Time is measured with time.perf_counter (monotonic, high-resolution wall clock).
No external benchmarking library is required.
"""

import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NAV_PAYLOAD = {
    "user_id": "perf-test-user",
    "current_zone": "A",
    "destination": "ST",
    "priority": "fast_exit",
}

# Dedicated IP bucket — performance tests run multiple calls so need their own window
_NAV_HEADERS = {"X-Forwarded-For": "10.204.0.1"}


def _timed_get(url: str) -> tuple[int, float]:
    """Returns (status_code, elapsed_seconds)."""
    start = time.perf_counter()
    resp = client.get(url)
    elapsed = time.perf_counter() - start
    return resp.status_code, elapsed


def _timed_post(url: str, payload: dict, headers: dict | None = None) -> tuple[int, float]:
    """Returns (status_code, elapsed_seconds)."""
    start = time.perf_counter()
    resp = client.post(url, json=payload, headers=headers or {})
    elapsed = time.perf_counter() - start
    return resp.status_code, elapsed


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

class TestEndpointLatency:
    """Each endpoint must respond within its threshold on *warm* paths."""

    def test_health_endpoint_latency(self):
        status, elapsed = _timed_get("/health")
        assert status == 200
        assert elapsed < 0.1, f"Health endpoint too slow: {elapsed:.3f}s (limit: 0.1s)"

    def test_crowd_status_latency(self):
        status, elapsed = _timed_get("/crowd/status")
        assert status == 200
        assert elapsed < 0.2, f"/crowd/status too slow: {elapsed:.3f}s (limit: 0.2s)"

    def test_wait_times_latency(self):
        status, elapsed = _timed_get("/crowd/wait-times")
        assert status == 200
        assert elapsed < 0.2, f"/crowd/wait-times too slow: {elapsed:.3f}s (limit: 0.2s)"

    def test_analytics_insights_latency(self):
        status, elapsed = _timed_get("/analytics/insights")
        assert status == 200
        assert elapsed < 0.2, f"/analytics/insights too slow: {elapsed:.3f}s (limit: 0.2s)"

    def test_navigate_suggest_latency(self):
        """Navigation is the most expensive path; allow up to 500 ms."""
        status, elapsed = _timed_post("/navigate/suggest", _NAV_PAYLOAD, _NAV_HEADERS)
        # 200 = success, 422 = validation — both count as "responded in time"
        assert status in (200, 422)
        assert elapsed < 0.5, f"/navigate/suggest too slow: {elapsed:.3f}s (limit: 0.5s)"


class TestConsistentLatency:
    """Run each expensive endpoint 3× and check the average stays within bounds."""

    def test_navigate_consistent_across_calls(self):
        times = []
        for _ in range(3):
            _, elapsed = _timed_post("/navigate/suggest", _NAV_PAYLOAD, _NAV_HEADERS)
            times.append(elapsed)
        avg = sum(times) / len(times)
        assert avg < 0.5, f"Navigation average latency too high: {avg:.3f}s over 3 calls"

    def test_analytics_consistent_across_calls(self):
        times = []
        for _ in range(3):
            _, elapsed = _timed_get("/analytics/insights")
            times.append(elapsed)
        avg = sum(times) / len(times)
        assert avg < 0.2, f"Analytics average latency too high: {avg:.3f}s over 3 calls"
