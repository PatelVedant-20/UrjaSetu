"""Unit tests for Phase 3 forecast evaluation metrics, dataset fixtures, and evaluation harness."""

from __future__ import annotations

import json

import pytest

from tests.fixtures.forecast.evaluator import ForecastEvaluator, ScenarioEvaluationReport
from tests.fixtures.forecast.loader import (
    get_forecast_fixtures_dir,
    list_available_forecast_scenarios,
    load_forecast_manifest,
    load_forecast_scenario,
)
from tests.fixtures.forecast.metrics import (
    compute_all_metrics,
    mean_absolute_error,
    mean_bias_error,
    normalized_mae,
    root_mean_squared_error,
    safe_mape,
    symmetric_mape,
)


class TestMetricsCalculation:
    """Test pure mathematical metric calculations against hand-calculated values."""

    def test_mean_absolute_error(self) -> None:
        actuals = [1.0, 2.0, 3.0, 4.0]
        preds = [1.2, 1.8, 3.5, 4.0]
        # Diff: 0.2, 0.2, 0.5, 0.0 -> sum = 0.9 / 4 = 0.225
        assert mean_absolute_error(actuals, preds) == 0.225

    def test_root_mean_squared_error(self) -> None:
        actuals = [1.0, 2.0, 3.0]
        preds = [2.0, 2.0, 4.0]
        # Diff: 1.0, 0.0, 1.0 -> sq: 1.0, 0.0, 1.0 -> sum = 2.0 / 3 = 0.66667 -> sqrt = 0.8165
        assert root_mean_squared_error(actuals, preds) == 0.8165

    def test_mean_bias_error(self) -> None:
        actuals = [2.0, 2.0, 2.0]
        # Over-forecasting
        preds_high = [2.5, 2.5, 2.5]
        assert mean_bias_error(actuals, preds_high) == 0.5

        # Under-forecasting
        preds_low = [1.5, 1.5, 1.5]
        assert mean_bias_error(actuals, preds_low) == -0.5

    def test_safe_mape_zero_denominator_protection(self) -> None:
        # Array with exact zero actuals (representing night solar)
        actuals = [0.0, 0.0, 2.0, 4.0]
        preds = [0.0, 0.1, 2.2, 3.6]

        # Standard MAPE would raise ZeroDivisionError or produce inf.
        # safe_mape filters points < threshold (0.1)
        # Remaining pairs: (2.0, 2.2) err=0.1, (4.0, 3.6) err=0.1 -> mean err = 0.1 (10.0%)
        val = safe_mape(actuals, preds, threshold=0.1)
        assert val == 10.0

    def test_safe_mape_all_zeros_returns_none(self) -> None:
        actuals = [0.0, 0.0, 0.0]
        preds = [0.0, 0.0, 0.0]
        assert safe_mape(actuals, preds, threshold=0.1) is None

    def test_symmetric_mape(self) -> None:
        actuals = [0.0, 2.0, 4.0]
        preds = [0.0, 2.0, 4.0]
        # Perfect forecast with zeros
        assert symmetric_mape(actuals, preds) == 0.0

        actuals = [2.0]
        preds = [4.0]
        # 2 * |2 - 4| / (2 + 4) = 4 / 6 = 66.67%
        assert symmetric_mape(actuals, preds) == 66.67

    def test_normalized_mae(self) -> None:
        actuals = [2.0, 4.0]
        preds = [2.5, 4.5]
        # MAE = 0.5 kW. Capacity = 5.0 kW -> nMAE = (0.5 / 5.0) * 100 = 10.0%
        assert normalized_mae(actuals, preds, capacity_kw=5.0) == 10.0

    def test_invalid_inputs_raise_errors(self) -> None:
        with pytest.raises(ValueError, match="Length mismatch"):
            mean_absolute_error([1.0], [1.0, 2.0])

        with pytest.raises(ValueError, match="empty"):
            mean_absolute_error([], [])

        with pytest.raises(ValueError, match="Capacity must be positive"):
            normalized_mae([1.0], [1.0], capacity_kw=-5.0)

    def test_compute_all_metrics(self) -> None:
        actuals = [0.0, 1.0, 2.0, 3.0]
        preds = [0.0, 1.1, 2.2, 2.9]
        res = compute_all_metrics(actuals, preds, capacity_kw=5.0, zero_threshold=0.5)
        assert res.sample_count == 4
        assert res.evaluated_intervals == 3  # >= 0.5 (1.0, 2.0, 3.0)
        assert res.skipped_intervals == 1  # 0.0
        assert res.nmae_percent is not None


class TestForecastDatasets:
    """Validate schema adherence and referential integrity of synthetic forecast datasets."""

    def test_manifest_contains_required_scenarios(self) -> None:
        manifest = load_forecast_manifest()
        scenarios = manifest.get("scenarios", {})
        required = [
            "normal_solar_day",
            "cloudy_day",
            "low_generation_day",
            "high_generation_day",
            "normal_household_demand",
            "unusual_demand",
            "missing_historical_telemetry",
        ]
        for req in required:
            assert req in scenarios, f"Missing required scenario: {req}"

    @pytest.mark.parametrize(
        "scenario_name",
        [
            "normal_solar_day",
            "cloudy_day",
            "low_generation_day",
            "high_generation_day",
            "normal_household_demand",
            "unusual_demand",
            "missing_historical_telemetry",
        ],
    )
    def test_scenario_schema_conformance(self, scenario_name: str) -> None:
        data = load_forecast_scenario(scenario_name)

        # Top-level fields
        assert "_scenario_id" in data
        assert "title" in data
        assert "forecast_type" in data
        assert "site_id" in data
        assert "total_intervals" in data
        assert len(data["forecast_points"]) == 96
        assert len(data["actual_readings"]) == 96

        # Check forecast run (Entity 11)
        run = data["forecast_run"]
        assert "id" in run
        assert run["forecast_type"] in {"solar", "load", "surplus"}
        assert "provider" in run
        assert "model_version" in run
        assert "horizon_start" in run
        assert "horizon_end" in run
        assert run["status"] == "completed"

        # Check forecast points (Entity 12)
        for pt in data["forecast_points"]:
            assert "id" in pt
            assert pt["forecast_run_id"] == run["id"]
            assert pt["site_id"] == data["site_id"]
            assert "interval_start" in pt
            assert "interval_end" in pt
            assert isinstance(pt["predicted_kw"], int | float)
            assert isinstance(pt["predicted_kwh"], int | float)
            assert 0.0 <= pt["confidence"] <= 1.0
            assert pt["lower_bound"] <= pt["upper_bound"]

        # Check actual readings (Entity 10)
        for a_pt in data["actual_readings"]:
            assert "id" in a_pt
            assert "meter_id" in a_pt
            assert "interval_start" in a_pt
            assert "interval_end" in a_pt
            assert a_pt["quality_status"] in {"valid", "missing"}

    def test_referential_integrity_against_seed(self) -> None:
        fixtures_dir = get_forecast_fixtures_dir()
        sites_file = fixtures_dir.parent / "sites.json"
        with open(sites_file, encoding="utf-8") as f:
            sites_data = json.load(f)
        valid_site_ids = {s["id"] for s in sites_data["sites"]}

        for sc_name in list_available_forecast_scenarios():
            data = load_forecast_scenario(sc_name)
            assert data["site_id"] in valid_site_ids, f"Invalid site_id in {sc_name}"


class TestForecastEvaluatorHarness:
    """Test end-to-end evaluation harness and reporting."""

    def test_evaluate_all_scenarios(self) -> None:
        evaluator = ForecastEvaluator()
        reports = evaluator.evaluate_all()
        assert len(reports) == 7

        for rep in reports:
            assert isinstance(rep, ScenarioEvaluationReport)
            assert rep.metrics.sample_count > 0
            assert rep.metrics.mae_kw >= 0.0
            assert rep.metrics.rmse_kw >= 0.0

    def test_missing_historical_telemetry_evaluation(self) -> None:
        evaluator = ForecastEvaluator()
        # Missing scenario has 8 missing intervals
        rep = evaluator.evaluate_scenario("missing_historical_telemetry", skip_missing=True)
        assert rep.metrics.sample_count == 88  # 96 - 8 = 88 evaluated
        assert rep.metrics.mae_kw >= 0.0

    def test_format_summary_table(self) -> None:
        evaluator = ForecastEvaluator()
        reports = evaluator.evaluate_all()
        table = evaluator.format_summary_table(reports)
        assert "Scenario ID" in table
        assert "normal_solar_day" in table
        assert "cloudy_day" in table
        assert "unusual_demand" in table
