"""
tests/test_live_alerts.py
--------------------------
Tests for the live re-routing alert and cooldown logic.

Scenarios covered
-----------------
- No history → no alert
- Same-zone source/destination → no alert
- No meaningful route change → no alert
- Better route found → alert triggered
- Dismissed alert cooldown → same reroute suppressed within 5 minutes
- Dismissed alert expired → alert reappears after cooldown
"""

from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.google_services import firestore_client
from app.models.crowd_models import EventPhase
import pytest

client = TestClient(app)

# Dedicated IP so tests never exhaust the navigation rate-limit bucket
_HEADERS = {"X-Forwarded-For": "10.201.0.1"}


def _nav_state(
    source="A",
    destination="ST",
    route=None,
    current_zone_index=0,
    dismissed_fingerprint="",
    dismissed_at="",
    wait_minutes=10,
):
    """Helper to build a minimal navigation state document."""
    return {
        "source": source,
        "destination": destination,
        "route": route or ["A", "Corridor_1", "Corridor_3", "ST"],
        "current_zone_index": current_zone_index,
        "dismissed_fingerprint": dismissed_fingerprint,
        "dismissed_at": dismissed_at,
        "priority": "fast_exit",
        "constraints": [],
        "event_phase": EventPhase.live.value,
        "wait_minutes": wait_minutes,
        "timestamp": datetime.now().isoformat(),
    }


@pytest.fixture(autouse=True)
def clean_mock_store():
    """Reset in-memory Firestore mock before every test."""
    firestore_client._MOCK_STORE.clear()


# ---------------------------------------------------------------------------
# Basic guard tests
# ---------------------------------------------------------------------------


def test_no_history_returns_no_alert():
    res = client.get("/navigate/alerts/missing-user", headers=_HEADERS)
    assert res.status_code == 200
    assert res.json()["requires_reroute"] is False


def test_same_zone_returns_no_alert():
    firestore_client.save_navigation_request(
        "user-same",
        _nav_state(source="A", destination="A", route=["A"], current_zone_index=0),
    )
    res = client.get("/navigate/alerts/user-same", headers=_HEADERS)
    assert res.status_code == 200
    assert res.json()["requires_reroute"] is False


def test_no_meaningful_change_returns_no_alert(monkeypatch):
    from app.api import routes_navigation

    def mock_find(*args, **kwargs):
        return ["A", "Corridor_1", "Corridor_3", "ST"]

    monkeypatch.setattr(routes_navigation, "find_best_route", mock_find)

    firestore_client.save_navigation_request("user-no-change", _nav_state())
    res = client.get("/navigate/alerts/user-no-change", headers=_HEADERS)
    assert res.status_code == 200
    assert res.json()["requires_reroute"] is False


# ---------------------------------------------------------------------------
# Alert trigger test
# ---------------------------------------------------------------------------


def test_better_route_returns_alert(monkeypatch):
    from app.api import routes_navigation

    def mock_find(*args, **kwargs):
        return ["A", "Corridor_2", "ST"]

    def mock_wait(route, density_map):
        if route == ["A", "Corridor_1", "Corridor_3", "ST"]:
            return 15
        return 5

    monkeypatch.setattr(routes_navigation, "find_best_route", mock_find)
    monkeypatch.setattr(routes_navigation, "estimate_wait_minutes", mock_wait)

    firestore_client.save_navigation_request("user-alert", _nav_state())
    res = client.get("/navigate/alerts/user-alert", headers=_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert data["requires_reroute"] is True
    assert data["new_navigation"] is not None
    assert data["new_navigation"]["estimated_wait_minutes"] == 5


# ---------------------------------------------------------------------------
# Cooldown / fingerprint suppression tests
# ---------------------------------------------------------------------------


def test_dismissed_alert_suppressed_within_cooldown(monkeypatch):
    """Same reroute dismissed 1 minute ago must NOT reappear."""
    from app.api import routes_navigation

    new_route = ["A", "Corridor_2", "ST"]
    fingerprint = "-".join(new_route)
    dismissed_at = (datetime.now() - timedelta(minutes=1)).isoformat()

    def mock_find(*args, **kwargs):
        return new_route

    def mock_wait(route, density_map):
        return 5 if route == new_route else 15

    monkeypatch.setattr(routes_navigation, "find_best_route", mock_find)
    monkeypatch.setattr(routes_navigation, "estimate_wait_minutes", mock_wait)

    firestore_client.save_navigation_request(
        "user-cooldown",
        _nav_state(dismissed_fingerprint=fingerprint, dismissed_at=dismissed_at),
    )
    res = client.get("/navigate/alerts/user-cooldown", headers=_HEADERS)
    assert res.status_code == 200
    assert res.json()["requires_reroute"] is False


def test_dismissed_alert_reappears_after_cooldown(monkeypatch):
    """Same reroute dismissed 10 minutes ago MUST reappear (cooldown expired)."""
    from app.api import routes_navigation

    new_route = ["A", "Corridor_2", "ST"]
    fingerprint = "-".join(new_route)
    dismissed_at = (datetime.now() - timedelta(minutes=10)).isoformat()

    def mock_find(*args, **kwargs):
        return new_route

    def mock_wait(route, density_map):
        return 5 if route == new_route else 15

    monkeypatch.setattr(routes_navigation, "find_best_route", mock_find)
    monkeypatch.setattr(routes_navigation, "estimate_wait_minutes", mock_wait)

    firestore_client.save_navigation_request(
        "user-cooldown-expired",
        _nav_state(dismissed_fingerprint=fingerprint, dismissed_at=dismissed_at),
    )
    res = client.get("/navigate/alerts/user-cooldown-expired", headers=_HEADERS)
    assert res.status_code == 200
    assert res.json()["requires_reroute"] is True


# ---------------------------------------------------------------------------
# Accept / dismiss endpoint tests
# ---------------------------------------------------------------------------


def test_accept_reroute_saves_new_route():
    """POST /navigate/accept persists the accepted route."""
    firestore_client.save_navigation_request("user-accept", _nav_state())
    new_route = ["A", "Corridor_2", "ST"]
    res = client.post(
        "/navigate/accept/user-accept",
        json=new_route,
        headers=_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"

    stored = firestore_client.get_user_history("user-accept")
    assert stored["route"] == new_route
    assert stored["current_zone_index"] == 0
    assert stored["dismissed_fingerprint"] == ""


def test_dismiss_reroute_records_fingerprint():
    """POST /navigate/dismiss records fingerprint for cooldown."""
    firestore_client.save_navigation_request("user-dismiss", _nav_state())
    dismissed_route = ["A", "Corridor_2", "ST"]
    res = client.post(
        "/navigate/dismiss/user-dismiss",
        json=dismissed_route,
        headers=_HEADERS,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "dismissed"

    stored = firestore_client.get_user_history("user-dismiss")
    assert stored["dismissed_fingerprint"] == "-".join(dismissed_route)
    assert stored["dismissed_at"] != ""


def test_accept_reroute_unknown_user_returns_404():
    res = client.post(
        "/navigate/accept/no-such-user",
        json=["A", "ST"],
        headers=_HEADERS,
    )
    assert res.status_code == 404
