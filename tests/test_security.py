"""
tests/test_security.py
-----------------------
Validates the Phase 9 security hardening:
  - Security headers present on every response
  - CORS origin list reflects debug mode
  - Rate limiter returns 429 after threshold is exceeded
  - Input validation rejects oversized / empty payloads
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_NAV_PAYLOAD = {
    "user_id": "test-user",
    "current_zone": "A",
    "destination": "ST",
    "priority": "fast_exit",
}

_VALID_CHAT_PAYLOAD = {
    "user_id": "test-user",
    "message": "What items are prohibited?",
}


# ---------------------------------------------------------------------------
# 1. Security headers
# ---------------------------------------------------------------------------


class TestSecurityHeaders:
    """Every non-static response must carry the required security headers."""

    def _get_headers(self) -> dict:
        resp = client.get("/health")
        assert resp.status_code == 200
        return resp.headers

    def test_x_content_type_options(self):
        assert self._get_headers().get("x-content-type-options") == "nosniff"

    def test_x_frame_options(self):
        assert self._get_headers().get("x-frame-options") == "DENY"

    def test_referrer_policy(self):
        assert (
            self._get_headers().get("referrer-policy")
            == "strict-origin-when-cross-origin"
        )

    def test_content_security_policy_present(self):
        csp = self._get_headers().get("content-security-policy", "")
        assert "default-src" in csp

    def test_csp_blocks_frames(self):
        csp = self._get_headers().get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp


# ---------------------------------------------------------------------------
# 2. CORS origin configuration
# ---------------------------------------------------------------------------


class TestCorsConfiguration:
    """Ensures allowed_origins logic respects the debug flag."""

    def test_debug_mode_returns_wildcard_by_default(self):
        """With no ALLOWED_ORIGINS_RAW set, debug=True should yield ['*']."""
        # The test environment runs with debug=False + no raw origins by default,
        # but we can unit-test the property directly on a fresh Settings instance.
        from app.config import Settings

        # Simulate a debug settings object with no raw origins
        s = Settings(debug=True, allowed_origins_raw="")
        assert s.allowed_origins == ["*"]

    def test_prod_mode_no_origins_returns_empty(self):
        """debug=False + no ALLOWED_ORIGINS_RAW → empty list (blocks all cross-origin)."""
        from app.config import Settings

        s = Settings(debug=False, allowed_origins_raw="")
        assert s.allowed_origins == []

    def test_explicit_origins_always_respected(self):
        """Explicit ALLOWED_ORIGINS_RAW overrides the debug default."""
        from app.config import Settings

        s = Settings(
            debug=True,
            allowed_origins_raw="https://example.com,https://app.example.com",
        )
        assert s.allowed_origins == ["https://example.com", "https://app.example.com"]

    def test_origins_whitespace_stripped(self):
        from app.config import Settings

        s = Settings(
            debug=False, allowed_origins_raw="  https://a.com , https://b.com  "
        )
        assert s.allowed_origins == ["https://a.com", "https://b.com"]


# ---------------------------------------------------------------------------
# 3. Rate limiting — navigation endpoint
# ---------------------------------------------------------------------------


class TestNavigationRateLimit:
    """POST /navigate/suggest is capped at 10 req/min per IP."""

    # Use a dedicated IP subnet so these tests never interfere with other suites
    # Use a highly specific IP subnet to avoid collision with performance benchmarks
    _base_ip = "192.168.99."

    def test_rate_limit_triggers_after_threshold(self):
        """11th request within the window should return 429."""
        # Platinum Tier: Clear state to avoid pollution from other test files
        from app.middleware.rate_limiter import navigation_rate_limit

        navigation_rate_limit.store.clear()

        headers = {"X-Forwarded-For": f"{self._base_ip}10"}
        hit_429 = False
        for _ in range(12):
            resp = client.post(
                "/navigate/suggest",
                json=_VALID_NAV_PAYLOAD,
                headers=headers,
            )
            if resp.status_code == 429:
                hit_429 = True
                break
        assert hit_429, "Expected HTTP 429 after exceeding rate limit threshold"

    def test_rate_limit_response_has_retry_after(self):
        """429 response must include Retry-After header."""
        headers = {"X-Forwarded-For": f"{self._base_ip}11"}
        for _ in range(12):
            resp = client.post(
                "/navigate/suggest",
                json=_VALID_NAV_PAYLOAD,
                headers=headers,
            )
            if resp.status_code == 429:
                assert "retry-after" in resp.headers
                return
        pytest.fail("Rate limit was never triggered")


# ---------------------------------------------------------------------------
# 4. Rate limiting — chat endpoint
# ---------------------------------------------------------------------------


class TestChatRateLimit:
    """POST /assistant/chat is capped at 20 req/min per IP."""

    def test_chat_rate_limit_triggers(self):
        # Platinum Tier: Clear state
        from app.middleware.rate_limiter import chat_rate_limit

        chat_rate_limit.store.clear()

        headers = {"X-Forwarded-For": "192.168.100.10"}
        hit_429 = False
        for _ in range(22):
            resp = client.post(
                "/assistant/chat",
                json=_VALID_CHAT_PAYLOAD,
                headers=headers,
            )
            if resp.status_code == 429:
                hit_429 = True
                break
        assert hit_429, "Expected HTTP 429 after exceeding chat rate limit threshold"


# ---------------------------------------------------------------------------
# 5. Input validation — chat message bounds
# ---------------------------------------------------------------------------


class TestChatInputValidation:
    def test_empty_message_rejected(self):
        resp = client.post(
            "/assistant/chat",
            json={**_VALID_CHAT_PAYLOAD, "message": ""},
        )
        assert resp.status_code == 422

    def test_whitespace_only_message_rejected(self):
        # Validator strips whitespace, leaving an empty string that fails min_length=1
        resp = client.post(
            "/assistant/chat",
            json={**_VALID_CHAT_PAYLOAD, "message": "   "},
        )
        assert resp.status_code == 422

    def test_oversized_message_rejected(self):
        """501-char message must be rejected with 422."""
        resp = client.post(
            "/assistant/chat",
            json={**_VALID_CHAT_PAYLOAD, "message": "x" * 501},
        )
        assert resp.status_code == 422

    def test_maximum_valid_message_accepted(self):
        """Exactly 500 chars must pass validation (response may vary)."""
        resp = client.post(
            "/assistant/chat",
            json={**_VALID_CHAT_PAYLOAD, "message": "q" * 500},
        )
        # Can be 200 (answered) or 422 only if Pydantic rejects — not expected here
        assert resp.status_code != 422

    def test_missing_user_id_rejected(self):
        resp = client.post(
            "/assistant/chat",
            json={"message": "Hello"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 6. Input validation — navigation request bounds
# ---------------------------------------------------------------------------


class TestNavigationInputValidation:
    # Use a dedicated IP bucket so these tests don't hit the rate limit
    # Use a dedicated IP bucket to avoid rate-limit depletion from other suites
    _headers = {"X-Forwarded-For": "192.168.101.10"}

    def test_zone_id_too_long_rejected(self):
        """33-char zone ID exceeds max_length=32 and must return 422."""
        resp = client.post(
            "/navigate/suggest",
            json={**_VALID_NAV_PAYLOAD, "current_zone": "Z" * 33},
            headers=self._headers,
        )
        assert resp.status_code == 422

    def test_user_id_too_long_rejected(self):
        resp = client.post(
            "/navigate/suggest",
            json={**_VALID_NAV_PAYLOAD, "user_id": "u" * 65},
            headers=self._headers,
        )
        assert resp.status_code == 422

    def test_too_many_constraints_rejected(self):
        """More than 5 constraints must be rejected."""
        resp = client.post(
            "/navigate/suggest",
            json={**_VALID_NAV_PAYLOAD, "constraints": ["c"] * 6},
            headers=self._headers,
        )
        assert resp.status_code == 422

    def test_empty_user_id_rejected(self):
        resp = client.post(
            "/navigate/suggest",
            json={**_VALID_NAV_PAYLOAD, "user_id": ""},
            headers=self._headers,
        )
        assert resp.status_code == 422

    def test_user_note_too_long_rejected(self):
        resp = client.post(
            "/navigate/suggest",
            json={**_VALID_NAV_PAYLOAD, "user_note": "n" * 257},
            headers=self._headers,
        )
        assert resp.status_code == 422
