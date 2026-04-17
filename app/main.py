"""
main.py
--------
FastAPI application entry point for StadiumChecker.

This module initializes the FastAPI application, configures security middleware,
sets up CORS, and registers all API routers. It also mounts the static
frontend assets.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings, logger
from app.api import (
    routes_health,
    routes_crowd,
    routes_navigation,
    routes_assistant,
    routes_analytics,
)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security headers on every HTTP response.

    Keeps the CSP permissive enough for the SPA (Google Fonts CDN + inline
    styles) while blocking the most common injection vectors.
    """

    _HEADERS: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "0",  # Modern browsers prefer CSP over legacy XSS filter
        "Referrer-Policy": "strict-origin-when-cross-origin",
        # HSTS: enforce HTTPS for 1 year; include subdomains for production.
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        # Content Security Policy (CSP):
        # Allow same-origin scripts/styles and Google Fonts; block everything else.
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        ),
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request and inject security headers into the response."""
        response: Response = await call_next(request)
        for header, value in self._HEADERS.items():
            response.headers[header] = value
        return response


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and shutdown events."""
    origins = settings.allowed_origins
    logger.info(
        f"🚀 {settings.app_name} v{settings.app_version} initialized. "
        f"Debug={settings.debug} | CORS origins={origins or 'NONE (Prod)'} | "
        f"Docs={'ENABLED' if settings.docs_enabled else 'DISABLED'}"
    )
    if not settings.debug and not origins:
        logger.warning(
            "⚠️  ALLOWED_ORIGINS_RAW is not set in production. "
            "Cross-origin requests will be blocked."
        )
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "StadiumChecker — Intelligent Crowd Navigation Assistant. "
        "Suggests optimal routes through large venues based on real-time crowd density."
    ),
    # interactive docs configuration
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    lifespan=lifespan,
)

# 1. Security headers — applied before CORS so headers are always present
app.add_middleware(SecurityHeadersMiddleware)

# 2. CORS — environment-aware; wildcard only when debug=True
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# 3. Register route modules
app.include_router(routes_health.router)
app.include_router(routes_crowd.router)
app.include_router(routes_navigation.router)
app.include_router(routes_assistant.router)
app.include_router(routes_analytics.router)

# 4. Mount static frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

logger.info("✅ System initialized successfully.")
