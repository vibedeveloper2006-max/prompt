"""
tests/test_decision_engine.py
------------------------------
Unit tests for scorer and router logic.
"""

import pytest
from app.decision_engine.scorer import score_zone, score_all_zones
from app.decision_engine.router import find_best_route, estimate_wait_minutes
from app.config import ZONE_REGISTRY
from app.models.navigation_models import Priority


# ── Scorer ───────────────────────────────────────────────────────────────────

class TestScorer:
    def test_low_density_gives_high_score(self):
        result = score_zone("FC", current_density=10, trend="STABLE")
        assert result["score"] > 80

    def test_high_density_gives_low_score(self):
        result = score_zone("A", current_density=90, trend="INCREASING")
        assert result["score"] < 20

    def test_decreasing_trend_boosts_score(self):
        result_dec = score_zone("B", 50, "DECREASING")
        result_inc = score_zone("B", 50, "INCREASING")
        assert result_dec["score"] > result_inc["score"]

    def test_scoring_edge_case_zero_density(self):
        # 0 density + STABLE/DECREASING should give effectively max score (bounded to 100)
        result = score_zone("FC", current_density=0, trend="STABLE")
        assert result["score"] == 100

    def test_score_always_in_range(self):
        for zone_id in ZONE_REGISTRY:
            for density in [0, 50, 100]:
                for trend in ["INCREASING", "STABLE", "DECREASING"]:
                    s = score_zone(zone_id, density, trend)
                    assert 0 <= s["score"] <= 100
                    assert 0 <= s["confidence_score"] <= 100

    def test_score_all_zones_covers_all(self):
        density_map = {z: 50 for z in ZONE_REGISTRY}
        predictions = {z: {"trend": "STABLE"} for z in ZONE_REGISTRY}
        scores = score_all_zones(density_map, predictions)
        assert set(scores.keys()) == set(ZONE_REGISTRY.keys())


# ── Router ───────────────────────────────────────────────────────────────────

class TestRouter:
    def _mock_scores(self, value: int = 50) -> dict:
        return {z: {"score": value, "confidence_score": value} for z in ZONE_REGISTRY}

    def test_same_source_destination_returns_single_zone(self):
        route = find_best_route("A", "A", self._mock_scores())
        assert route == ["A"]

    def test_route_starts_at_source_ends_at_destination(self):
        route = find_best_route("A", "FC", self._mock_scores())
        assert route is not None
        assert route[0] == "A"
        assert route[-1] == "FC"

    def test_route_contains_only_valid_zones(self):
        route = find_best_route("A", "ST", self._mock_scores())
        assert route is not None
        for zone in route:
            assert zone in ZONE_REGISTRY

    def test_router_avoid_crowd_constraint(self):
        # A route from A to FC via Corridor_1 is physically shorter
        # Let's make Corridor_1 very congested
        scores = self._mock_scores(50)
        scores["Corridor_1"]["score"] = 10  # Highly congested
        scores["Corridor_2"]["score"] = 90  # Empty
        
        # Without constraints, distance might prefer Corridor_1
        # With avoid_crowd, penalty is multiplied, forcing it through Corridor_2
        route = find_best_route("A", "FC", scores, constraints=["avoid_crowd"])
        assert "Corridor_2" in route
        assert "Corridor_1" not in route

    def test_router_prefer_fastest_constraint(self):
        scores = self._mock_scores()
        scores["Corridor_1"]["score"] = 10  # Highly congested, but shorter route
        scores["Corridor_2"]["score"] = 90  # Empty
        
        # With prefer_fastest, congestion penalty is ignored (0)
        # So it takes the absolute shortest physical distance which is Corridor_1
        route = find_best_route("A", "FC", scores, constraints=["prefer_fastest"])
        assert "Corridor_1" in route

    def test_router_accessible_priority(self):
        # A to ST typically prefers Corridor_2 because it's 60+100=160
        # A to Corridor_1 -> B -> Corridor_3 -> ST is 50+40+70+120=280
        # But Corridor_2 is explicitly accessible: False
        scores = self._mock_scores(90) # Emptiness everywhere
        
        route_normal = find_best_route("A", "ST", scores, priority=Priority.fast_exit)
        assert "Corridor_2" in route_normal  # Normal takes the shorter path
        
        route_accessible = find_best_route("A", "ST", scores, priority=Priority.accessible)
        assert "Corridor_2" not in route_accessible # Skips steep stairs
        assert "Corridor_3" in route_accessible # Takes long detour

    def test_router_family_friendly_priority(self):
        # C is not family friendly. Route from ST to Corridor_2 vs ST to C to Corridor_2
        # We can just test that the penalty behaves without asserting exact route unless it diverges
        scores = self._mock_scores(50)
        route_family = find_best_route("ST", "A", scores, priority=Priority.family_friendly)
        # Should not go through C if alternative is viable
        assert "C" not in route_family

    def test_no_path_for_disconnected_graph(self):
        # Use a zone that has no neighbors by patching ZONE_REGISTRY temporarily
        from app.config import ZONE_REGISTRY as ZR
        ZR["ISOLATED"] = {"name": "Isolated", "type": "test", "capacity": 0, "neighbors": {}}
        route = find_best_route("ISOLATED", "A", self._mock_scores())
        assert route is None
        del ZR["ISOLATED"]

    def test_estimate_wait_high_density_higher_wait(self):
        route = ["A", "FC"]
        low_density = {"A": 20, "FC": 20}
        high_density = {"A": 85, "FC": 85}
        assert estimate_wait_minutes(route, high_density) > estimate_wait_minutes(route, low_density)
