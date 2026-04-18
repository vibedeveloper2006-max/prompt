"""
google_services/bigquery_client.py
------------------------------------
BigQuery integration layer for the StadiumChecker platform.

This module provides high-level functions to log crowd telemetry and query
historical congestion patterns. It includes a sophisticated bounded-mock
implementation to ensure system operation when GCP credentials are not present,
preventing memory leaks and request storms.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Setup BigQuery Client (Optional)
# ---------------------------------------------------------------------------
bq_client: Optional[Any] = None
if getattr(settings, "bigquery_enabled", False):
    try:
        from google.cloud import bigquery

        bq_client = bigquery.Client(
            project=settings.gcp_project_id if settings.gcp_project_id else None
        )
        logger.info("✅ BigQuery client initialized successfully.")
    except Exception as e:
        logger.warning(f"⚠️ BigQuery initialization failed (using mock): {e}")

# Bounded mock store — prevents memory growth in the Python process
_MAX_MOCK_EVENTS: int = 200
_MOCK_EVENTS: deque = deque(maxlen=_MAX_MOCK_EVENTS)

# Per-zone cooldown: collapses rapid writes into a manageable trickle
_LOG_COOLDOWN_SECONDS: int = 5
_last_log_time: Dict[str, float] = {}

TABLE_ID = "stadiumchecker.analytics.crowd_events"


def log_crowd_event(zone_id: str, density: int, timestamp: str) -> None:
    """Logs a single crowd data point to BigQuery for downstream analytics.

    In mock mode, this function is rate-gated per zone to prevent the simulation
    from overwhelming the local log store with redundant data points.
    """
    event = {"zone_id": zone_id, "density": density, "timestamp": timestamp}

    if bq_client is not None:
        try:
            errors = bq_client.insert_rows_json(TABLE_ID, [event])
            if not errors:
                logger.debug("Telemetry sent to BigQuery: %s", zone_id)
                return
            logger.error("BigQuery streaming error: %s", errors)
        except Exception as e:
            logger.error("BigQuery client failure: %s. Falling back to mock.", e)

    # Rate-gate the local mock log to keep data representative but compact
    now = time.monotonic()
    if (now - _last_log_time.get(zone_id, 0.0)) < _LOG_COOLDOWN_SECONDS:
        return

    _last_log_time[zone_id] = now
    _MOCK_EVENTS.append(event)
    logger.debug("Analytics [MOCK] logged for zone: %s", zone_id)


# --- Aggregation Cache (Internal) ---
_agg_cache: Dict[str, Any] = {}
_AGG_CACHE_TTL: int = 15


def query_peak_zones(top_n: int = 3) -> List[str]:
    """Queries the history for zones with the highest average congestion.

    Optimized with a 5-second internal cache to meet high-end latency requirements
    (e.g., < 200ms) even during simulation spikes.
    """
    now = time.monotonic()
    cache_key = f"peak_zones_{top_n}"

    if cache_key in _agg_cache:
        val, expiry = _agg_cache[cache_key]
        if now < expiry:
            return val

    if bq_client is not None:
        try:
            sql = f"""
                SELECT zone_id, AVG(density) as avg_density
                FROM `{TABLE_ID}`
                GROUP BY zone_id
                ORDER BY avg_density DESC
                LIMIT {top_n}
            """
            query_job = bq_client.query(sql)
            results = query_job.result()
            res = [row["zone_id"] for row in results]
            _agg_cache[cache_key] = (res, now + _AGG_CACHE_TTL)
            return res
        except Exception as e:
            logger.error("BigQuery SQL query failed: %s. Using mock data.", e)

    # Mock algorithm: group densities by zone and sort by average
    zone_totals: Dict[str, List[int]] = defaultdict(list)
    for evt in _MOCK_EVENTS:
        zone_totals[evt["zone_id"]].append(evt["density"])

    if not zone_totals:
        return []

    # Map-Reduce style aggregation
    averages = {zid: sum(vals) / len(vals) for zid, vals in zone_totals.items()}
    sorted_zones = sorted(averages, key=lambda k: averages[k], reverse=True)
    res = sorted_zones[:top_n]

    # Persistent cache for performance
    _agg_cache[cache_key] = (res, now + _AGG_CACHE_TTL)

    return res
