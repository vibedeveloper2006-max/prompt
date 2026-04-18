"""
tests/test_performance_optimizations.py
-----------------------------------------
Verifies resource-usage optimisations without breaking existing behaviour.

Covers:
  1. Density-map cache — burst calls within the same second share one result.
  2. Cache bypass for explicit `now` values — tests remain deterministic.
  3. Cache bounds — the TTL cache never exceeds MAX_ENTRIES hard cap.
  4. BigQuery mock bounded — _MOCK_EVENTS deque never exceeds _MAX_MOCK_EVENTS.
  5. BigQuery rate-gate — same zone is NOT logged twice within _LOG_COOLDOWN_SECONDS.
  6. BigQuery query_peak_zones correctness — returns highest-average-density zones.
  7. Firestore mock bounded — _MOCK_STORE never exceeds _MAX_MOCK_DOCS entries.
  8. predict_all_zones accepts a pre-computed density_map (no double call).
  9. End-to-end: /crowd/status + /crowd/wait-times in the same second share cache.
 10. End-to-end: /navigate/suggest latency is below 500ms budget (smoke).
"""

import time
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.crowd_engine.cache import _TTLCache
from app.crowd_engine.simulator import get_zone_density_map
from app.crowd_engine.predictor import predict_all_zones
from app.config import ZONE_REGISTRY

client = TestClient(app)


# ─── 1. Cache hit within the same clock-second ─────────────────────────────


def test_density_map_cache_hit():
    """Two immediate calls with no explicit `now` must return the *same* object."""
    result1 = get_zone_density_map()
    result2 = get_zone_density_map()
    # Must be identical dict content (deterministic within same second)
    assert result1 == result2


def test_density_map_cache_hit_same_reference():
    """The cached path should return the same dict object (not a copy)."""
    from app.crowd_engine.cache import crowd_cache

    crowd_cache._store.clear()  # force a cold miss
    r1 = get_zone_density_map()
    r2 = get_zone_density_map()
    assert r1 is r2  # same object from cache, not recomputed


# ─── 2. Cache bypassed for explicit `now` ──────────────────────────────────


def test_density_map_bypasses_cache_for_explicit_now():
    """Explicit `now` must bypass cache, so tests stay deterministic."""
    from app.crowd_engine.cache import crowd_cache

    t = datetime(2026, 1, 1, 14, 0, 0)
    crowd_cache._store.clear()
    r1 = get_zone_density_map(now=t)
    r2 = get_zone_density_map(now=t)
    # Values equal (same input) but must NOT be the same cached object
    assert r1 == r2
    cache_key = ("density_map", int(t.timestamp()))
    assert cache_key not in crowd_cache._store


# ─── 3. Cache hard entry cap ───────────────────────────────────────────────


def test_ttl_cache_max_entries_bounded():
    """_TTLCache never grows beyond its max_entries limit."""
    cache = _TTLCache(ttl=60, max_entries=5)
    for i in range(20):
        cache.set(f"key_{i}", i)
    assert len(cache._store) <= 5


def test_ttl_cache_evicts_expired_before_cap():
    """Expired entries are evicted on next write, reducing eviction pressure."""
    # Use a very short but non-zero TTL so the first entry is expired *after*
    # a small sleep but the second entry is still fresh when we read it.
    cache = _TTLCache(ttl=0.05, max_entries=10)
    cache.set("a", 1)
    time.sleep(0.06)  # "a" is now expired
    cache.set("b", 2)  # triggers eviction of expired "a"
    assert cache.get("a") is None
    assert cache.get("b") == 2


# ─── 4. BigQuery deque bounded ─────────────────────────────────────────────


def test_bigquery_mock_deque_bounded():
    """_MOCK_EVENTS deque must not grow beyond _MAX_MOCK_EVENTS."""
    from app.google_services import bigquery_client
    from app.google_services.bigquery_client import _MAX_MOCK_EVENTS, _MOCK_EVENTS

    # Reset state
    _MOCK_EVENTS.clear()
    bigquery_client._last_log_time.clear()

    # Insert well above the cap (bypass rate-gate by using distinct zone IDs)
    ts = "2026-01-01T10:00:00"
    for i in range(_MAX_MOCK_EVENTS + 50):
        fake_zone = f"FAKE_{i}"
        bigquery_client._last_log_time.pop(fake_zone, None)  # clear cooldown
        bigquery_client.log_crowd_event(fake_zone, 50, ts)

    assert len(_MOCK_EVENTS) <= _MAX_MOCK_EVENTS


# ─── 5. BigQuery rate-gate per zone ────────────────────────────────────────


def test_bigquery_rate_gate_suppresses_duplicates():
    """The same zone must not be logged twice within _LOG_COOLDOWN_SECONDS."""
    from app.google_services import bigquery_client
    from app.google_services.bigquery_client import _MOCK_EVENTS

    _MOCK_EVENTS.clear()
    bigquery_client._last_log_time.clear()

    ts = "2026-01-01T10:00:00"
    bigquery_client.log_crowd_event("GATE_A", 70, ts)  # first — should log
    bigquery_client.log_crowd_event("GATE_A", 72, ts)  # within cooldown — suppressed
    bigquery_client.log_crowd_event("GATE_A", 75, ts)  # within cooldown — suppressed

    events_for_gate = [e for e in _MOCK_EVENTS if e["zone_id"] == "GATE_A"]
    assert len(events_for_gate) == 1


# ─── 6. BigQuery query_peak_zones returns highest-average-density zones ────


def test_bigquery_query_peak_zones_correct_order():
    """query_peak_zones must return the zone with HIGHEST average density first."""
    from app.google_services import bigquery_client
    from app.google_services.bigquery_client import _MOCK_EVENTS

    _MOCK_EVENTS.clear()
    bigquery_client._last_log_time.clear()

    ts = "2026-01-01T10:00:00"
    # LOW_ZONE averages 20; HIGH_ZONE averages 90
    for zone, density in [("LOW_ZONE", 20), ("HIGH_ZONE", 90)]:
        bigquery_client._last_log_time.pop(zone, None)
        bigquery_client.log_crowd_event(zone, density, ts)

    results = bigquery_client.query_peak_zones(top_n=2)
    assert results[0] == "HIGH_ZONE"


# ─── 7. Firestore mock store bounded ───────────────────────────────────────


def test_firestore_mock_store_bounded():
    """_MOCK_STORE (OrderedDict) should never exceed _MAX_MOCK_DOCS entries."""
    from app.google_services import firestore_client
    from app.google_services.firestore_client import _MOCK_STORE, _MAX_MOCK_DOCS

    _MOCK_STORE.clear()

    for i in range(_MAX_MOCK_DOCS + 100):
        firestore_client._set_doc("crowd_snapshots", str(i), {"d": i}, f"crowd/{i}")

    assert len(_MOCK_STORE) <= _MAX_MOCK_DOCS


# ─── 8. predict_all_zones accepts pre-computed density_map ─────────────────


def test_predict_all_zones_accepts_density_map():
    """Passing density_map prevents an internal get_zone_density_map call."""
    fixed_time = datetime(2026, 6, 1, 14, 0, 0)
    prefetched = get_zone_density_map(now=fixed_time)

    with patch("app.crowd_engine.predictor.get_zone_density_map") as mock_get:
        result = predict_all_zones(now=fixed_time, density_map=prefetched)
        mock_get.assert_not_called()

    assert set(result.keys()) == set(ZONE_REGISTRY.keys())


# ─── 9. HTTP burst: /crowd/status + /crowd/wait-times share cache ──────────


def test_crowd_endpoints_share_density_cache(monkeypatch):
    """get_zone_density_map called twice with no `now` must share one computation.

    This unit test directly verifies the cache behaviour that drives the
    cross-endpoint optimisation: /crowd/status and /crowd/wait-times both call
    get_zone_density_map() with no explicit `now`, so the second call must
    return the same dict object from the cache without re-running _base_density.
    """
    from app.crowd_engine import simulator
    from app.crowd_engine.cache import crowd_cache

    # Cold start
    crowd_cache._store.clear()

    call_count = {"n": 0}
    original_base = simulator._base_density

    def counting_base_density(hour, zone_id, zone_seed, event_phase="live"):
        call_count["n"] += 1
        return original_base(hour, zone_id, zone_seed, event_phase)

    monkeypatch.setattr(simulator, "_base_density", counting_base_density)

    # First call — populates the cache
    r1 = simulator.get_zone_density_map()
    calls_first = call_count["n"]

    # Second call — must hit cache (same object, no new _base_density calls)
    r2 = simulator.get_zone_density_map()
    calls_second = call_count["n"]

    assert r1 is r2, "Second call must return the same cached dict object"
    assert calls_first == len(r1), "First call must compute all zones once"
    assert calls_second == calls_first, (
        f"Second call must not invoke _base_density again (cache miss). "
        f"Before: {calls_first}, After: {calls_second}"
    )


# ─── 10. /navigate/suggest latency smoke test ──────────────────────────────


def test_suggest_navigation_latency():
    """End-to-end suggest must complete within 500 ms (without live Gemini calls)."""
    zones = list(ZONE_REGISTRY.keys())
    payload = {
        "user_id": "perf_test_user",
        "current_zone": zones[0],
        "destination": zones[-1],
        "priority": "fast_exit",
    }
    start = time.perf_counter()
    r = client.post("/navigate/suggest", json=payload)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert r.status_code == 200
    assert elapsed_ms < 500, f"Suggest took {elapsed_ms:.0f} ms — over 500 ms budget"
