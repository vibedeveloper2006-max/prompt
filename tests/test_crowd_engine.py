"""
tests/test_crowd_engine.py
---------------------------
Unit tests for crowd simulation and prediction logic.
All tests use a fixed datetime to ensure deterministic results.
"""

from datetime import datetime
import pytest

from app.crowd_engine.simulator import (
    get_zone_density_map,
    get_zone_crowd_detail,
    _density_to_status,
    _is_peak_hour,
)
from app.crowd_engine.predictor import (
    predict_zone_density,
    predict_all_zones,
    _compute_flow_delta,
    _compute_time_delta,
)
from app.crowd_engine.wait_times import (
    calculate_service_wait_time,
    determine_wait_trend,
    get_wait_status
)
from app.config import ZONE_REGISTRY

# Fixed test time: 18:30 — inside the evening peak window
PEAK_TIME = datetime(2024, 1, 1, 18, 30)
OFF_PEAK_TIME = datetime(2024, 1, 1, 3, 0)


class TestSimulator:
    def test_density_map_covers_all_zones(self):
        density_map = get_zone_density_map(PEAK_TIME)
        assert set(density_map.keys()) == set(ZONE_REGISTRY.keys())

    def test_density_values_in_valid_range(self):
        density_map = get_zone_density_map(PEAK_TIME)
        for zone_id, density in density_map.items():
            assert 0 <= density <= 100, f"Zone {zone_id} density out of range: {density}"

    def test_peak_hour_detected_correctly(self):
        assert _is_peak_hour(18) is True
        assert _is_peak_hour(3) is False
        assert _is_peak_hour(12) is True

    def test_density_to_status_thresholds(self):
        assert _density_to_status(80) == "HIGH"
        assert _density_to_status(55) == "MEDIUM"
        assert _density_to_status(20) == "LOW"

    def test_zone_crowd_detail_structure(self):
        density_map = get_zone_density_map(PEAK_TIME)
        detail = get_zone_crowd_detail("A", density_map)
        assert "zone_id" in detail
        assert "name" in detail
        assert "density" in detail
        assert "status" in detail
        assert detail["status"] in ("LOW", "MEDIUM", "HIGH")

    def test_invalid_zone_raises_key_error(self):
        density_map = get_zone_density_map(PEAK_TIME)
        density_map["FAKE"] = 50
        with pytest.raises(KeyError):
            get_zone_crowd_detail("FAKE", density_map)


class TestPredictor:
    def test_prediction_has_required_keys(self):
        result = predict_zone_density("A", 60, PEAK_TIME)
        assert "zone_id" in result
        assert "current_density" in result
        assert "predicted_density" in result
        assert "trend" in result
        assert result["prediction_window_minutes"] == 30

    def test_predicted_density_in_valid_range(self):
        for density in [0, 50, 100]:
            result = predict_zone_density("FC", density, PEAK_TIME)
            assert 0 <= result["predicted_density"] <= 100

    def test_trend_is_valid_enum(self):
        valid_trends = {"INCREASING", "STABLE", "DECREASING"}
        result = predict_zone_density("B", 40, PEAK_TIME)
        assert result["trend"] in valid_trends

    def test_predict_all_zones_returns_all(self):
        predictions = predict_all_zones(PEAK_TIME)
        assert set(predictions.keys()) == set(ZONE_REGISTRY.keys())

    def test_prediction_with_increasing_inflow(self):
        # High inflow means prediction should increase
        res = predict_zone_density("A", 50, PEAK_TIME, inflow_rate=30, outflow_rate=5)
        assert res["predicted_density"] > 50
        assert res["trend"] == "INCREASING"

    def test_prediction_with_decreasing_flow(self):
        # High outflow means prediction should decrease
        res = predict_zone_density("A", 50, PEAK_TIME, inflow_rate=5, outflow_rate=30)
        assert res["predicted_density"] < 50
        assert res["trend"] == "DECREASING"

    def test_event_phase_impact_on_prediction(self):
        # Food court should be much busier during halftime phase
        # Baseline density at an offpeak time
        normal_res = predict_zone_density("FC", 40, OFF_PEAK_TIME, event_phase="live")
        halftime_res = predict_zone_density("FC", 40, OFF_PEAK_TIME, event_phase="halftime")
        assert halftime_res["predicted_density"] > normal_res["predicted_density"]


class TestFlowPredictor:
    """Tests for the flow-based prediction layer added on top of time-based logic."""

    # ── Unit: _compute_flow_delta ────────────────────────────────────────────

    def test_flow_delta_positive_when_inflow_exceeds_outflow(self):
        assert _compute_flow_delta(inflow_rate=20, outflow_rate=5) == 15

    def test_flow_delta_negative_when_outflow_exceeds_inflow(self):
        assert _compute_flow_delta(inflow_rate=5, outflow_rate=20) == -15

    def test_flow_delta_zero_when_balanced(self):
        assert _compute_flow_delta(inflow_rate=10, outflow_rate=10) == 0

    def test_flow_delta_rounds_fractional_values(self):
        # 7.6 - 2.1 = 5.5 → rounds to 6
        assert _compute_flow_delta(7.6, 2.1) == round(7.6 - 2.1)

    # ── Unit: _compute_time_delta ────────────────────────────────────────────

    def test_time_delta_positive_approaching_peak(self):
        # 07:45 — not yet peak, but 30 min later = 08:15 which IS peak (08–10)
        just_before_peak = datetime(2024, 1, 1, 7, 45)
        assert _compute_time_delta(just_before_peak) == +15

    def test_time_delta_negative_leaving_peak(self):
        # 09:45 — peak now, but 30 min later = 10:15 which is outside (08–10)
        leaving_peak = datetime(2024, 1, 1, 9, 45)
        assert _compute_time_delta(leaving_peak) == -12

    def test_time_delta_stable_mid_peak(self):
        # 18:30 deep inside peak window (17–21); next 30 min still inside
        assert _compute_time_delta(PEAK_TIME) == +3

    def test_time_delta_stable_off_peak(self):
        assert _compute_time_delta(OFF_PEAK_TIME) == -3

    # ── Integration: combined predict_zone_density ───────────────────────────

    def test_flow_increases_predicted_density(self):
        """High inflow should push predicted_density above time-only prediction."""
        baseline = predict_zone_density("A", 50, PEAK_TIME)
        with_inflow = predict_zone_density("A", 50, PEAK_TIME, inflow_rate=20, outflow_rate=0)
        assert with_inflow["predicted_density"] > baseline["predicted_density"]

    def test_flow_decreases_predicted_density(self):
        """High outflow should pull predicted_density below time-only prediction."""
        baseline = predict_zone_density("A", 50, PEAK_TIME)
        with_outflow = predict_zone_density("A", 50, PEAK_TIME, inflow_rate=0, outflow_rate=20)
        assert with_outflow["predicted_density"] < baseline["predicted_density"]

    def test_response_contains_flow_fields(self):
        result = predict_zone_density("FC", 40, PEAK_TIME, inflow_rate=10, outflow_rate=3)
        assert "inflow_rate" in result
        assert "outflow_rate" in result
        assert "flow_delta" in result
        assert result["inflow_rate"] == 10
        assert result["outflow_rate"] == 3
        assert result["flow_delta"] == 7

    # ── Boundary clamping ────────────────────────────────────────────────────

    def test_density_never_exceeds_100(self):
        # Density 95 + massive inflow → must clamp at 100
        result = predict_zone_density("ST", 95, PEAK_TIME, inflow_rate=50, outflow_rate=0)
        assert result["predicted_density"] <= 100

    def test_density_never_below_zero(self):
        # Density 5 + massive outflow → must clamp at 0
        result = predict_zone_density("C", 5, OFF_PEAK_TIME, inflow_rate=0, outflow_rate=50)
        assert result["predicted_density"] >= 0

    # ── Trend derivation ────────────────────────────────────────────────────

    def test_trend_increasing_when_large_net_positive(self):
        # Off-peak time_delta = -3; inflow=30, outflow=0 → net = -3+30 = +27
        result = predict_zone_density("B", 40, OFF_PEAK_TIME, inflow_rate=30, outflow_rate=0)
        assert result["trend"] == "INCREASING"

    def test_trend_decreasing_when_large_net_negative(self):
        # PEAK_TIME time_delta = +3; inflow=0, outflow=30 → net = 3-30 = -27
        result = predict_zone_density("A", 60, PEAK_TIME, inflow_rate=0, outflow_rate=30)
        assert result["trend"] == "DECREASING"

    def test_trend_stable_when_flow_cancels_time_delta(self):
        # Off-peak time_delta = -3; inflow=3, outflow=0 → net = 0 (inside ±3 threshold)
        result = predict_zone_density("FC", 50, OFF_PEAK_TIME, inflow_rate=3, outflow_rate=0)
        assert result["trend"] == "STABLE"

    # ── predict_all_zones with flow_rates ────────────────────────────────────

    def test_predict_all_zones_accepts_flow_rates(self):
        flow_rates = {"A": {"inflow_rate": 15, "outflow_rate": 5}}
        predictions = predict_all_zones(PEAK_TIME, flow_rates=flow_rates)
        assert predictions["A"]["flow_delta"] == 10
        assert predictions["A"]["inflow_rate"] == 15

    def test_predict_all_zones_defaults_to_zero_flow_for_missing_zones(self):
        flow_rates = {}  # no overrides
        predictions = predict_all_zones(PEAK_TIME, flow_rates=flow_rates)
        for zone_id, pred in predictions.items():
            assert pred["inflow_rate"] == 0.0
            assert pred["outflow_rate"] == 0.0
            assert pred["flow_delta"] == 0

class TestWaitTimes:
    def test_calculate_wait_time_gates(self):
        # 80% full gate = 30 * (0.8)^2 = 30 * 0.64 = ~19
        wait = calculate_service_wait_time("A", {"type": "gate"}, 80)
        assert wait == int(30 * (0.8 ** 2))

    def test_calculate_wait_time_restrooms(self):
        # 50% full restroom = 15 * 0.5 = 7
        wait = calculate_service_wait_time("RR_1", {"type": "restroom"}, 50)
        assert wait == int(15 * 0.5)

    def test_calculate_wait_time_amenities(self):
        # 100% full food court = 25 * 1.0 = 25
        wait = calculate_service_wait_time("FC", {"type": "amenity"}, 100)
        assert wait == 25
        
    def test_calculate_wait_time_corridors_zero(self):
        wait = calculate_service_wait_time("Corridor_1", {"type": "corridor"}, 100)
        assert wait == 0

    def test_calculate_wait_time_under_20_percent_zero(self):
        wait = calculate_service_wait_time("A", {"type": "gate"}, 15)
        assert wait == 0

    def test_determine_wait_trend_increasing(self):
        assert determine_wait_trend(50, {"predicted_density": 60}) == "INCREASING"

    def test_determine_wait_trend_decreasing(self):
        assert determine_wait_trend(50, {"predicted_density": 40}) == "DECREASING"

    def test_determine_wait_trend_stable(self):
        assert determine_wait_trend(50, {"predicted_density": 52}) == "STABLE"

    def test_get_wait_status(self):
        assert get_wait_status(2) == "LOW"
        assert get_wait_status(10) == "MODERATE"
        assert get_wait_status(20) == "HIGH"

