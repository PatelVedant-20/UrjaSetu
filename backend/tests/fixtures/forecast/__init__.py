"""Forecast fixtures and evaluation tooling for UrjaSetu Phase 3."""

from tests.fixtures.forecast.evaluator import (
    ForecastEvaluator,
    ScenarioEvaluationReport,
)
from tests.fixtures.forecast.loader import (
    extract_evaluation_vectors,
    get_forecast_fixtures_dir,
    list_available_forecast_scenarios,
    load_forecast_manifest,
    load_forecast_scenario,
)
from tests.fixtures.forecast.metrics import (
    ForecastMetricsResult,
    compute_all_metrics,
    mean_absolute_error,
    mean_bias_error,
    normalized_mae,
    root_mean_squared_error,
    safe_mape,
    symmetric_mape,
)

__all__ = [
    "ForecastEvaluator",
    "ForecastMetricsResult",
    "ScenarioEvaluationReport",
    "compute_all_metrics",
    "extract_evaluation_vectors",
    "get_forecast_fixtures_dir",
    "list_available_forecast_scenarios",
    "load_forecast_manifest",
    "load_forecast_scenario",
    "mean_absolute_error",
    "mean_bias_error",
    "normalized_mae",
    "root_mean_squared_error",
    "safe_mape",
    "symmetric_mape",
]
