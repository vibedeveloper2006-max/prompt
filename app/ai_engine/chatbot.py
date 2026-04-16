"""
ai_engine/chatbot.py
--------------------
Event Assistant chatbot for the StadiumChecker Cup venue.

Design constraints
------------------
- Intent classification is deterministic — no AI involved in deciding what
  the question is about.
- Structured facts (policy, timings, services) are resolved from
  app/config_data.py before Gemini is ever called.
- Gemini is used ONLY to phrase the final response in natural language.
- Route and wait-time questions are intercepted and redirected to the
  deterministic route planner.
- Falls back to a safety message when Gemini is unavailable or over quota.
"""

import json
import logging
from typing import Optional

import google.generativeai as genai  # noqa: PLC0415

from app.config import settings
from app.config_data import EVENT_INFO, VENUE_POLICY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gemini initialisation (optional)
# ---------------------------------------------------------------------------
try:
    if settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(settings.gemini_model)
    else:
        _model = None
        logger.warning("Gemini config missing — chatbot running in structured-data-only mode.")
except Exception as exc:
    _model = None
    logger.error("Failed to initialise Gemini: %s", exc)


# ---------------------------------------------------------------------------
# System instruction (used only when Gemini is available)
# ---------------------------------------------------------------------------
_SYSTEM_INSTRUCTION = f"""
You are the Official Event Assistant for the {EVENT_INFO['event_name']} at {EVENT_INFO['venue']}.

### CRITICAL RULES
1. You may ONLY use the grounded fact context provided in each message.
   Never invent venue policies, item rules, or timings.
2. If asked about routes, wait times, or crowd levels, respond EXACTLY:
   "Please use the Route Planner on this page for live route and wait information."
3. If confident factual context is missing, say:
   "I don't have that information — please ask a visible steward or visit the Information Desk near Gate A."
4. Keep answers short, plain, and scannable (prefer bullet points for lists).
5. Never speculate about safety, medical, or emergency guidance.

You will receive grounded context prepended to each question.
Use that context to answer — do not add information beyond it.
"""


# ---------------------------------------------------------------------------
# Intent classification helpers
# ---------------------------------------------------------------------------

_ROUTE_KEYWORDS = (
    "route", "path", "way to", "how to get", "fastest", "navigate",
    "wait", "queue", "line", "how long", "restroom wait", "bathroom",
    "which gate", "crowd level",
)

_PROHIBITED_KEYWORDS = (
    "not allowed", "prohibited", "banned", "can i bring", "forbidden",
    "allowed in", "items", "what can", "bring into",
)

_BAG_KEYWORDS = ("bag", "backpack", "clear bag", "bag policy", "purse", "luggage")

_ACCESSIBILITY_KEYWORDS = (
    "wheelchair", "disabled", "accessible", "accessibility", "hearing loop",
    "sign language", "mobility", "assistance dog", "quiet area", "ambulant",
    "sensory",
)

_RE_ENTRY_KEYWORDS = (
    "re-entry", "re entry", "reentry", "leave and come back",
    "exit and return", "come back in", "go back in",
)

_RESTRICTED_KEYWORDS = (
    "restricted", "vip", "hospitality", "media zone", "staff only",
    "press", "pitch side", "north stand",
)

_TIMING_KEYWORDS = (
    "when does", "what time", "kick off", "kick-off", "start time",
    "gates open", "halftime", "half time", "end time", "full time",
    "schedule", "programme",
)

_TICKET_KEYWORDS = ("ticket", "qr code", "season ticket", "digital ticket", "paper ticket")

_FIRST_AID_KEYWORDS = ("first aid", "medical", "defibrillator", "emergency", "injured", "ambulance")

_LOST_PROPERTY_KEYWORDS = ("lost", "found", "lost property", "missing", "left behind")


def _classify_intent(query_lower: str) -> Optional[str]:
    """Returns an intent label or None if no grounded intent matches."""
    if any(k in query_lower for k in _ROUTE_KEYWORDS):
        return "route"
    if any(k in query_lower for k in _PROHIBITED_KEYWORDS):
        return "prohibited"
    if any(k in query_lower for k in _BAG_KEYWORDS):
        return "bag"
    if any(k in query_lower for k in _ACCESSIBILITY_KEYWORDS):
        return "accessibility"
    if any(k in query_lower for k in _RE_ENTRY_KEYWORDS):
        return "reentry"
    if any(k in query_lower for k in _RESTRICTED_KEYWORDS):
        return "restricted"
    if any(k in query_lower for k in _TIMING_KEYWORDS):
        return "timing"
    if any(k in query_lower for k in _TICKET_KEYWORDS):
        return "ticket"
    if any(k in query_lower for k in _FIRST_AID_KEYWORDS):
        return "first_aid"
    if any(k in query_lower for k in _LOST_PROPERTY_KEYWORDS):
        return "lost_property"
    return None


def _build_grounded_context(intent: str) -> str:
    """Maps an intent to a concise structured-data excerpt for Gemini."""
    if intent == "prohibited":
        items = "\n".join(f"- {i}" for i in VENUE_POLICY["prohibited_items"])
        return f"Prohibited items at this event:\n{items}"

    if intent == "bag":
        return f"Bag policy: {VENUE_POLICY['bag_policy']}"

    if intent == "accessibility":
        services = "\n".join(f"- {s}" for s in VENUE_POLICY["accessibility_services"])
        return f"Accessibility services available:\n{services}"

    if intent == "reentry":
        return f"Re-entry rules: {VENUE_POLICY['re_entry_rules']}"

    if intent == "restricted":
        return f"Restricted areas: {VENUE_POLICY['restricted_areas']}"

    if intent == "timing":
        phases = "\n".join(f"- {p}" for p in EVENT_INFO["key_phases"])
        return (
            f"Event: {EVENT_INFO['event_name']}\n"
            f"Date: {EVENT_INFO['date']}\n"
            f"Kick-off: {EVENT_INFO['kick_off_time']}\n"
            f"Schedule:\n{phases}"
        )

    if intent == "ticket":
        return f"Ticket guidance: {VENUE_POLICY['ticket_guidance']}"

    if intent == "first_aid":
        return f"First-aid information: {VENUE_POLICY['first_aid']}"

    if intent == "lost_property":
        return f"Lost property: {VENUE_POLICY['lost_property']}"

    return ""


# ---------------------------------------------------------------------------
# Direct (no-Gemini) fallback responses for each intent
# ---------------------------------------------------------------------------

def _direct_response(intent: str) -> str:
    """Concise plain-text response from structured data when Gemini is unavailable."""
    ctx = _build_grounded_context(intent)
    if ctx:
        return ctx
    return "I don't have that information — please ask a steward or visit the Information Desk near Gate A."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_chat_response(query: str, history: list = None) -> str:
    """
    Returns a grounded answer for the attendee's question.

    Flow:
    1. Classify intent deterministically.
    2. Route/wait → redirect immediately (no AI).
    3. Grounded intent → fetch structured context.
        a. If Gemini available → ask Gemini to phrase it naturally.
        b. If Gemini absent  → return structured text directly.
    4. Unknown intent → safety fallback (no invention).
    """
    query_lower = query.lower()
    intent = _classify_intent(query_lower)

    # ── Route / wait handoff ─────────────────────────────────────────────────
    if intent == "route":
        return (
            "Please use the Route Planner on this page for live route recommendations "
            "and wait-time estimates — it uses real-time crowd data to find the best path for you."
        )

    # ── Grounded intent ──────────────────────────────────────────────────────
    if intent:
        context = _build_grounded_context(intent)

        if not _model:
            return _direct_response(intent)

        try:
            grounded_prompt = (
                f"{_SYSTEM_INSTRUCTION}\n\n"
                f"### Grounded Context\n{context}\n\n"
                f"### Attendee Question\n{query}"
            )
            # Include only the last 4 turns to stay within context limits
            history_turns = []
            for msg in (history or [])[-4:]:
                role = "user" if msg.get("role") == "user" else "model"
                history_turns.append({"role": role, "parts": [msg.get("content", "")]})

            contents = [{"role": "user", "parts": [grounded_prompt]}]
            contents.extend(history_turns)
            # Re-append query so it's the final user turn
            if history_turns:
                contents.append({"role": "user", "parts": [query]})

            response = _model.generate_content(
                contents,
                request_options={"timeout": settings.gemini_timeout_seconds},
            )
            return response.text.strip()

        except Exception as exc:
            logger.error("Gemini phrasing failed: %s", exc)
            return _direct_response(intent)

    # ── Unknown intent ───────────────────────────────────────────────────────
    if not _model:
        return (
            "I'm currently offline. For event and venue help, please visit the "
            "Information Desk near Gate A or speak to a steward."
        )

    try:
        # Pass the full system instruction but include NO invented context
        unknown_prompt = (
            f"{_SYSTEM_INSTRUCTION}\n\n"
            f"### Attendee Question\n{query}\n\n"
            f"Note: No specific grounded context is available for this question. "
            f"Respond using rule 3 only."
        )
        response = _model.generate_content(
            [{"role": "user", "parts": [unknown_prompt]}],
            request_options={"timeout": settings.gemini_timeout_seconds},
        )
        return response.text.strip()
    except Exception as exc:
        logger.error("Gemini fallback failed: %s", exc)
        return (
            "I'm experiencing technical difficulties. Please ask a steward "
            "or visit the Information Desk near Gate A."
        )
