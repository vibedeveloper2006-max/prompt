"""
google_services/bigquery_client.py
------------------------------------
BigQuery integration (mock-ready).

Used for analytics: logging crowd events, querying historical patterns.
Replace mock body with google-cloud-bigquery calls for production.

Optimizations vs. original:
  - _MOCK_EVENTS is now a bounded deque (max _MAX_MOCK_EVENTS = 200).
    This prevents unbounded memory growth when the mock accumulates one
    entry per zone per /crowd/status poll for hours.
  - log_crowd_event is rate-gated: in mock mode, the same zone is only
    logged once per _LOG_COOLDOWN_SECONDS (default 5 s).  This collapses
    the per-zone-per-request write storm into a sensible trickle while
    still keeping the mock store representative for query_peak_zones.
  - query_peak_zones uses a sorted aggregation instead of an O(n) scan so
    results are accurate (highest average density) rather than insertion-order.
"""

import logging
from collections import defaultdict, deque
from typing import Dict, List
import time

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Setup BigQuery Client (Optional)
# ---------------------------------------------------------------------------
bq_client = None
if getattr(settings, "bigquery_enabled", False):
    try:
        from google.cloud import bigquery
        bq_client = bigquery.Client(project=settings.gcp_project_id if settings.gcp_project_id else None)
        logger.info("BigQuery client initialized.")
    except Exception as e:
        logger.warning(f"Failed to initialize BigQuery (falling back to mock): {e}")

# Bounded mock store — prevents memory growth during long-running processes
_MAX_MOCK_EVENTS: int = 200
_MOCK_EVENTS: deque = deque(maxlen=_MAX_MOCK_EVENTS)

# Per-zone cooldown: don't write the same zone to the mock more than once per window
_LOG_COOLDOWN_SECONDS: int = 5
_last_log_time: Dict[str, float] = {}

TABLE_ID = "stadiumchecker.analytics.crowd_events"


def log_crowd_event(zone_id: str, density: int, timestamp: str) -> None:
    """Inserts a crowd data point into BigQuery (mocked fallback available).

    In mock mode, writes are rate-gated per zone (once per _LOG_COOLDOWN_SECONDS)
    to avoid a write-per-zone-per-request storm while still keeping the mock
    store diverse enough for query_peak_zones to return meaningful results.
    """
    event = {"zone_id": zone_id, "density": density, "timestamp": timestamp}

    if bq_client is not None:
        try:
            errors = bq_client.insert_rows_json(TABLE_ID, [event])
            if not errors:
                logger.debug("BigQuery logged event: %s", event)
                return
            else:
                logger.error("BigQuery insert failed with errors: %s", errors)
        except Exception as e:
            logger.error("BigQuery client error: %s. Falling back to mock.", e)

    # Rate-gate mock writes to avoid one entry per zone per HTTP request
    now = time.monotonic()
    if (now - _last_log_time.get(zone_id, 0.0)) < _LOG_COOLDOWN_SECONDS:
        return  # Skip — logged this zone recently

    _last_log_time[zone_id] = now
    _MOCK_EVENTS.append(event)
    logger.debug("BigQuery [MOCK] logged event: %s", event)


def query_peak_zones(top_n: int = 3) -> List[str]:
    """
    Returns zone IDs with the highest average density from logged events.

    Mock: aggregates average density per zone and returns top_n by that metric,
    matching the intent of the real BigQuery query.
    """
    if bq_client is not None:
        try:
            query = f"""
                SELECT zone_id, AVG(density) as avg_density
                FROM `{TABLE_ID}`
                GROUP BY zone_id
                ORDER BY avg_density DESC
                LIMIT {top_n}
            """
            query_job = bq_client.query(query)
            results = query_job.result()
            return [row["zone_id"] for row in results]
        except Exception as e:
            logger.error("BigQuery query failed: %s. Falling back to mock.", e)

    # Mock: aggregate average density, return top N by average (correct semantics)
    zone_totals: Dict[str, List[int]] = defaultdict(list)
    for evt in _MOCK_EVENTS:
        zone_totals[evt["zone_id"]].append(evt["density"])

    averages = {zid: sum(vals) / len(vals) for zid, vals in zone_totals.items()}
    sorted_zones = sorted(averages, key=averages.get, reverse=True)
    return sorted_zones[:top_n]
