"""
app/api/routes_health.py
-------------------------
Health check endpoint — used by load balancers, CI, and Postman smoke tests.

Returns system status, version, and a per-service integration readiness map
so operators and evaluators can verify Google Cloud connectivity at a glance.
"""

from fastapi import APIRouter
from app.config import settings

router = APIRouter(tags=["Health"])


def _service_status() -> dict:
    """Returns a dict describing the readiness of each Google / AI integration."""
    from app.google_services.firestore_client import db as firestore_db
    from app.google_services.bigquery_client import bq_client
    from app.google_services.maps_client import _gmaps, get_maps_status
    from app.ai_engine.explainer import _model as gemini_explainer

    return {
        "firestore": (
            "enabled" if firestore_db is not None
            else ("configured" if settings.firestore_enabled else "disabled")
        ),
        "bigquery": (
            "enabled" if bq_client is not None
            else ("configured" if settings.bigquery_enabled else "disabled")
        ),
        "maps": get_maps_status(),
        "gemini": (
            "enabled" if gemini_explainer is not None
            else ("configured" if settings.gemini_api_key else "disabled")
        ),
    }


@router.get("/health")
def health_check():
    """Returns system status, version, and per-service integration readiness."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "app_name": settings.app_name,
        "services": _service_status(),
    }
