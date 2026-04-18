"""
ai_engine/explainer.py
-----------------------
Calls Gemini to produce a human-readable explanation of the navigation decision.

Responsibilities:
  - Accept a prompt string from prompt_builder.py
  - Call Gemini (or return a deterministic fallback when the key is absent/exhausted)
  - Return plain text — never structured data

Design rules:
  - Gemini is NEVER used for routing decisions — only for human-readable explanation.
  - The model client is a module-level singleton to avoid re-initializing the SDK
    on every navigation request.
  - Falls back gracefully so a Gemini outage never breaks the navigation response.
"""

import logging

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level singleton — initialized once at import time.
# Re-using the same model object avoids API-key reconfiguration overhead on
# every POST /navigate/suggest call.
# ---------------------------------------------------------------------------
_model = None

if settings.gemini_api_key:
    try:
        genai.configure(api_key=settings.gemini_api_key)
        _model = genai.GenerativeModel(settings.gemini_model)
        logger.info("Explainer: Gemini model '%s' ready.", settings.gemini_model)
    except Exception as exc:
        logger.error("Explainer: Failed to initialize Gemini model: %s", exc)
else:
    logger.warning(
        "Explainer: GEMINI_API_KEY not set — returning fallback explanations."
    )


def get_ai_explanation(prompt: str) -> str:
    """
    Sends `prompt` to Gemini and returns the explanation string.

    Falls back to a generic explanation if the model is not configured
    or if the call fails — this prevents the entire navigation response
    from failing because of an optional AI layer.
    """
    if _model is None:
        return _fallback_explanation()

    try:
        response = _model.generate_content(
            prompt,
            request_options={"timeout": settings.gemini_timeout_seconds},
        )
        return response.text.strip()
    except Exception as exc:
        logger.error("Explainer: Gemini call failed: %s", exc)
        return _fallback_explanation()


def _fallback_explanation() -> str:
    return (
        "This route was selected because it passes through the least congested zones "
        "based on current crowd density readings. Follow the suggested path for the "
        "quickest and most comfortable journey."
    )
