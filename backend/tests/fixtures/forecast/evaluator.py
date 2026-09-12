"""Evaluation harness orchestrating dataset loading and metric computation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from tests.fixtures.forecast.loader import (
    extract_evaluation_vectors,
    list_available_forecast_scenarios,
)
from tests.fixtures.forecast.metrics import ForecastMetricsResult, compute_all_metrics


@dataclass(frozen=True)
class ScenarioEvaluationReport:
    """Evaluation report for a single forecast scenario."""

    scenario_id: str
    title: str
    forecast_type: str
    site_id: str
    metrics: ForecastMetricsResult
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "forecast_type": self.forecast_type,
            "site_id": self.site_id,
            "metrics": asdict(self.metrics),
            "metadata": self.metadata,
        }


class ForecastEvaluator:
    """Evaluation harness for assessing forecast model accuracy against synthetic ground truth."""

    def __init__(self, zero_threshold: float = 0.1) -> None:
        self.zero_threshold = zero_threshold

    def evaluate_scenario(
        self,
        scenario_name: str,
        skip_missing: bool = True,
    ) -> ScenarioEvaluationReport:
        """Evaluate accuracy metrics for a specific scenario."""
        actuals, predictions, metadata = extract_evaluation_vectors(
            scenario_name, skip_missing=skip_missing
        )

        capacity_kw = metadata.get("asset_capacity_kw")
        metrics = compute_all_metrics(
            actuals=actuals,
            predictions=predictions,
            capacity_kw=capacity_kw,
            zero_threshold=self.zero_threshold,
        )

        return ScenarioEvaluationReport(
            scenario_id=metadata.get("scenario_id", scenario_name),
            title=metadata.get("title", ""),
            forecast_type=metadata.get("forecast_type", ""),
            site_id=metadata.get("site_id", ""),
            metrics=metrics,
            metadata=metadata,
        )

    def evaluate_all(self) -> list[ScenarioEvaluationReport]:
        """Evaluate all available forecast scenarios in data/synthetic/forecast/."""
        scenarios = list_available_forecast_scenarios()
        return [self.evaluate_scenario(sc) for sc in scenarios]

    @staticmethod
    def format_summary_table(reports: list[ScenarioEvaluationReport]) -> str:
        """Format reports into a readable ASCII comparison table."""
        header = (
            f"{'Scenario ID':<30} | {'Type':<6} | {'MAE (kW)':<9} | "
            f"{'RMSE (kW)':<10} | {'Bias (kW)':<10} | {'Safe MAPE':<10} | {'nMAE (%)':<9}"
        )
        sep = "-" * len(header)
        rows = [header, sep]

        for rep in reports:
            m = rep.metrics
            mape_str = f"{m.safe_mape_percent:.2f}%" if m.safe_mape_percent is not None else "N/A"
            nmae_str = f"{m.nmae_percent:.2f}%" if m.nmae_percent is not None else "N/A"
            row = (
                f"{rep.scenario_id:<30} | "
                f"{rep.forecast_type:<6} | "
                f"{m.mae_kw:<9.4f} | "
                f"{m.rmse_kw:<10.4f} | "
                f"{m.mean_bias_kw:<+10.4f} | "
                f"{mape_str:<10} | "
                f"{nmae_str:<9}"
            )
            rows.append(row)

        return "\n".join(rows)
