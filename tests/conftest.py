"""
tests/conftest.py
------------------
Shared pytest fixtures for the StadiumChecker test suite.

Centralizing fixtures here eliminates boilerplate duplication across test
modules and ensures all test classes use consistent, isolated IP buckets
and payload shapes.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.rate_limiter import (
    navigation_rate_limit,
    chat_rate_limit,
    analytics_rate_limit,
)


@pytest.fixture(scope="session")
def test_client() -> TestClient:
    """Single TestClient instance shared across the session for speed."""
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=False)
def clear_rate_limits():
    """Clears all rate limiter stores before each test that requests this fixture."""
    navigation_rate_limit.store.clear()
    chat_rate_limit.store.clear()
    analytics_rate_limit.store.clear()
    yield
    navigation_rate_limit.store.clear()
    chat_rate_limit.store.clear()
    analytics_rate_limit.store.clear()


@pytest.fixture
def nav_payload() -> dict:
    """Standard navigation request payload."""
    return {
        "user_id": "fixture-user",
        "current_zone": "A",
        "destination": "ST",
        "priority": "fast_exit",
    }


@pytest.fixture
def chat_payload() -> dict:
    """Standard chat request payload."""
    return {
        "user_id": "fixture-user",
        "message": "What items are prohibited?",
    }


@pytest.fixture
def nav_headers() -> dict:
    """Dedicated IP bucket for navigation fixture tests."""
    return {"X-Forwarded-For": "10.250.0.1"}


@pytest.fixture
def chat_headers() -> dict:
    """Dedicated IP bucket for chat fixture tests."""
    return {"X-Forwarded-For": "10.251.0.1"}
