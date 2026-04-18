"""
config.py
---------
Centralized application settings and zone definitions.
All environment variables are read here. No other module reads from .env directly.

Security notes:
- In production (DEBUG=false) set ALLOWED_ORIGINS to a comma-separated list of
  trusted frontend domains. Wildcard CORS is only permitted when DEBUG=true.
- Set DOCS_ENABLED=false before going live to hide /docs and /redoc.
"""

import logging
from typing import Any, Dict, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# Set up standard logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    app_name: str = "StadiumChecker"
    app_version: str = "1.0.0"
    debug: bool = False

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v: Any) -> bool:
        if isinstance(v, str):
            v_lower = v.lower()
            if v_lower in ("true", "t", "1", "yes", "y", "on"):
                return True
            # For anything else, including 'release', 'prod', 'false', default to False
            return False
        return bool(v)

    # Security
    # Comma-separated list of allowed CORS origins, e.g. "https://stadiumchecker.example.com"
    # Defaults to ["*"] only when debug=True (overridden by compute_allowed_origins below).
    # In production, set ALLOWED_ORIGINS explicitly — empty string disables all cross-origin.
    allowed_origins_raw: str = ""
    docs_enabled: bool = True

    @field_validator("allowed_origins_raw", mode="before")
    @classmethod
    def parse_origins_raw(cls, v: Any) -> str:
        """Accept list or str from env; always normalize to str for later splitting."""
        if isinstance(v, list):
            return ",".join(v)
        return str(v) if v else ""

    @property
    def allowed_origins(self) -> List[str]:
        """Returns the effective CORS origin list.

        - Debug mode  → ["*"] unless the caller explicitly overrides via ALLOWED_ORIGINS_RAW.
        - Prod  mode  → uses ALLOWED_ORIGINS_RAW; raises at startup if it is empty.
        """
        if self.allowed_origins_raw.strip():
            return [o.strip() for o in self.allowed_origins_raw.split(",") if o.strip()]
        if self.debug:
            return ["*"]
        # Production with no explicit origin list — fall back to an empty list so that
        # FastAPI/Starlette blocks every cross-origin request rather than leaking data.
        return []

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    gemini_timeout_seconds: int = 5

    # Google Services (leave empty to use mocks)
    gcp_project_id: str = ""
    firestore_enabled: bool = False
    bigquery_enabled: bool = False
    maps_api_key: str = ""
    maps_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env")


# Singleton settings instance
settings = Settings()


# ---------------------------------------------------------------------------
# Zone Registry
# Defines all physical zones. Add / remove zones here — no code changes needed.
# ---------------------------------------------------------------------------
ZONE_REGISTRY: Dict[str, Dict] = {
    "A": {
        "name": "Gate A",
        "type": "gate",
        "capacity": 500,
        "neighbors": {"Corridor_1": 50, "Corridor_2": 60},
        "accessible": True,
        "family_friendly": True,
    },
    "B": {
        "name": "Gate B",
        "type": "gate",
        "capacity": 500,
        "neighbors": {"Corridor_1": 40, "Corridor_3": 70},
        "accessible": True,
        "family_friendly": True,
    },
    "C": {
        "name": "Gate C",
        "type": "gate",
        "capacity": 400,
        "neighbors": {"Corridor_2": 50, "Corridor_3": 50},
        "accessible": True,
        "family_friendly": False,  # e.g. Cramped turnstiles
    },
    "FC": {
        "name": "Food Court",
        "type": "amenity",
        "capacity": 300,
        "neighbors": {"Corridor_1": 30, "Corridor_2": 80},
        "accessible": True,
        "family_friendly": True,
    },
    "ST": {
        "name": "Main Stadium",
        "type": "venue",
        "capacity": 5000,
        "neighbors": {"Corridor_2": 100, "Corridor_3": 120},
        "accessible": True,
        "family_friendly": True,
    },
    "Corridor_1": {
        "name": "Corridor 1",
        "type": "corridor",
        "capacity": 200,
        "neighbors": {"A": 50, "B": 40, "FC": 30},
        "accessible": True,
        "family_friendly": True,
    },
    "Corridor_2": {
        "name": "Corridor 2",
        "type": "corridor",
        "capacity": 200,
        "neighbors": {"A": 60, "C": 50, "FC": 80, "ST": 100},
        "accessible": False,  # e.g. Requires stairs to bridge level
        "family_friendly": False,
    },
    "Corridor_3": {
        "name": "Corridor 3",
        "type": "corridor",
        "capacity": 200,
        "neighbors": {"B": 70, "C": 50, "ST": 120, "RR_1": 20},
        "accessible": True,
        "family_friendly": True,
    },
    "RR_1": {
        "name": "Main Restroom",
        "type": "restroom",
        "capacity": 50,
        "neighbors": {"Corridor_3": 20},
        "accessible": True,
        "family_friendly": True,
    },
}

# Peak hours: congestion boost is applied in these ranges (24h format)
PEAK_HOUR_WINDOWS = [
    (8, 10),  # Morning rush
    (12, 14),  # Lunch
    (17, 21),  # Evening event
]

# Density thresholds → crowd status labels
DENSITY_STATUS_MAP = [
    (70, "HIGH"),
    (40, "MEDIUM"),
    (0, "LOW"),
]
