"""
main.py
--------
FastAPI application entry point.

- Creates the app with environment-aware docs visibility
- Registers all routers
- Configures CORS from settings (wildcard only in debug mode)
- Injects security headers on every response
"""

from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings, logger
from app.api import routes_health, routes_crowd, routes_navigation, routes_assistant, routes_analytics


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security headers on every HTTP response.

    Keeps the CSP permissive enough for the SPA (Google Fonts CDN + inline
    styles) while blocking the most common injection vectors.
    """

    _HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "0",  # Modern browsers prefer CSP over legacy XSS filter
        "Referrer-Policy": "strict-origin-when-cross-origin",
        # HSTS: enforce HTTPS for 1 year; include subdomains for production.
        # NOTE: only effective when served over TLS (Cloud Run handles TLS termination).
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
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
        response: Response = await call_next(request)
        for header, value in self._HEADERS.items():
            response.headers[header] = value
        return response


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    origins = settings.allowed_origins
    logger.info(
        f"🚀 {settings.app_name} v{settings.app_version} — "
        f"debug={settings.debug} | CORS origins={origins or 'none (production)'} | "
        f"docs={'enabled' if settings.docs_enabled else 'disabled'}"
    )
    if not settings.debug and not origins:
        logger.warning(
            "⚠️  ALLOWED_ORIGINS_RAW is not set and DEBUG is False. "
            "Cross-origin requests will be blocked. "
            "Set ALLOWED_ORIGINS_RAW in your environment for production deployments."
        )
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "StadiumChecker — Intelligent Crowd Navigation Assistant. "
        "Suggests optimal routes through large venues based on real-time crowd density."
    ),
    # Hide interactive docs in strict production deployments
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    lifespan=lifespan,
)

# Security headers — applied before CORS so headers are always present
app.add_middleware(SecurityHeadersMiddleware)

# CORS — environment-aware; wildcard only when debug=True
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,  # credentials + wildcard is forbidden by the spec anyway
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# Register route modules
app.include_router(routes_health.router)
app.include_router(routes_crowd.router)
app.include_router(routes_navigation.router)
app.include_router(routes_assistant.router)
app.include_router(routes_analytics.router)

# Mount static frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

logger.info("✅ StadiumChecker API + Frontend successfully initialized and ready for traffic.")
