"""
api/routes_health.py
---------------------
Health check endpoint — used by load balancers, CI, and Postman smoke tests.
"""

from fastapi import APIRouter
from app.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Returns system status and version."""
    return {"status": "ok", "version": settings.app_version}
