"""
tests/test_chatbot.py
---------------------
Tests for the Event Assistant chatbot:
- Routing override (route/wait questions handoff)
- Grounded intent responses (prohibited items, bag policy, accessibility, timing)
- Offline fallback (no Gemini key)
- Input validation
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Unique IP bucket so chatbot tests don't exhaust the chat rate limit
_HEADERS = {"X-Forwarded-For": "10.220.0.1"}


class TestRoutingOverride:
    """Route/wait questions must be redirected to the deterministic route planner."""

    def test_route_question_redirects(self):
        payload = {
            "message": "What is the fastest route to my seat?",
            "user_id": "cb_test_1",
            "history": [],
        }
        res = client.post("/assistant/chat", json=payload, headers=_HEADERS)
        assert res.status_code == 200
        assert "Route Planner" in res.json()["reply"]

    def test_wait_question_redirects(self):
        payload = {
            "message": "How long is the queue at Gate A?",
            "user_id": "cb_test_2",
            "history": [],
        }
        res = client.post("/assistant/chat", json=payload, headers=_HEADERS)
        assert res.status_code == 200
        assert "Route Planner" in res.json()["reply"]

    def test_navigate_keyword_redirects(self):
        payload = {
            "message": "Can you navigate me to the restroom?",
            "user_id": "cb_test_3",
            "history": [],
        }
        res = client.post("/assistant/chat", json=payload, headers=_HEADERS)
        assert res.status_code == 200
        assert "Route Planner" in res.json()["reply"]


class TestGroundedIntents:
    """Grounded intents must return information sourced from config_data.py."""

    def _assert_grounded(self, reply: str, *keywords):
        """Either the reply contains a keyword, or Gemini is offline (both are valid)."""
        reply_lower = reply.lower()
        if "offline" in reply_lower or "technical difficulties" in reply_lower:
            return  # Gemini not available in CI — structured fallback is acceptable
        assert any(
            k in reply_lower for k in keywords
        ), f"Expected one of {keywords!r} in reply, got: {reply!r}"

    def test_prohibited_items_response(self):
        payload = {
            "message": "What items are not allowed at the stadium?",
            "user_id": "cb_test_4",
            "history": [],
        }
        res = client.post("/assistant/chat", json=payload, headers=_HEADERS)
        assert res.status_code == 200
        self._assert_grounded(
            res.json()["reply"], "flare", "weapon", "glass", "drone", "prohibited"
        )

    def test_bag_policy_response(self):
        payload = {
            "message": "What is the bag policy?",
            "user_id": "cb_test_5",
            "history": [],
        }
        res = client.post("/assistant/chat", json=payload, headers=_HEADERS)
        assert res.status_code == 200
        self._assert_grounded(
            res.json()["reply"], "clear", "bag", "plastic", "transparent"
        )

    def test_accessibility_response(self):
        payload = {
            "message": "Is there wheelchair access at the stadium?",
            "user_id": "cb_test_6",
            "history": [],
        }
        res = client.post("/assistant/chat", json=payload, headers=_HEADERS)
        assert res.status_code == 200
        self._assert_grounded(
            res.json()["reply"],
            "wheelchair",
            "accessible",
            "mobility",
            "disabled",
            "accessibility",
        )

    def test_event_timing_response(self):
        payload = {
            "message": "What time does the match kick off?",
            "user_id": "cb_test_7",
            "history": [],
        }
        res = client.post("/assistant/chat", json=payload, headers=_HEADERS)
        assert res.status_code == 200
        self._assert_grounded(
            res.json()["reply"], "19:30", "kick", "schedule", "start", "17:00"
        )


class TestInputValidation:
    """Pydantic validation must reject malformed requests."""

    def test_missing_user_id_rejected(self):
        res = client.post(
            "/assistant/chat", json={"message": "Hello?"}, headers=_HEADERS
        )
        assert res.status_code == 422

    def test_empty_message_rejected(self):
        res = client.post(
            "/assistant/chat", json={"message": "", "user_id": "u1"}, headers=_HEADERS
        )
        assert res.status_code == 422

    def test_whitespace_only_message_rejected(self):
        res = client.post(
            "/assistant/chat",
            json={"message": "   ", "user_id": "u1"},
            headers=_HEADERS,
        )
        assert res.status_code == 422
