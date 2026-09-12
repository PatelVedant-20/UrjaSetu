"""Forecast evaluation metrics for UrjaSetu Phase 3.

Pure calculation tooling for evaluating forecast accuracy against actual telemetry readings.
Adheres to CERC/CEA Indian grid standards, handling zero-denominator edge cases (e.g. night solar).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ForecastMetricsResult:
    """Evaluation summary metrics for a forecast evaluation run."""

    sample_count: int
    mae_kw: float
    rmse_kw: float
    mean_bias_kw: float
    safe_mape_percent: float | None
    smape_percent: float
    nmae_percent: float | None
    evaluated_intervals: int
    skipped_intervals: int

    def to_dict(self) -> dict[str, float | int | None]:
        """Convert metrics result to clean dictionary."""
        return asdict(self)


def mean_absolute_error(actuals: Sequence[float], predictions: Sequence[float]) -> float:
    """Calculate Mean Absolute Error (MAE) in kW.

    MAE = (1 / n) * sum(|actual_i - predicted_i|)
    """
    if len(actuals) != len(predictions):
        raise ValueError(
            f"Length mismatch: {len(actuals)} actuals vs {len(predictions)} predictions"
        )
    if not actuals:
        raise ValueError("Cannot calculate MAE on empty sequences")

    total = sum(abs(a - p) for a, p in zip(actuals, predictions, strict=True))
    return round(total / len(actuals), 4)


def root_mean_squared_error(actuals: Sequence[float], predictions: Sequence[float]) -> float:
    """Calculate Root Mean Squared Error (RMSE) in kW.

    RMSE = sqrt((1 / n) * sum((actual_i - predicted_i)^2))
    """
    if len(actuals) != len(predictions):
        raise ValueError(
            f"Length mismatch: {len(actuals)} actuals vs {len(predictions)} predictions"
        )
    if not actuals:
        raise ValueError("Cannot calculate RMSE on empty sequences")

    total_sq = sum((a - p) ** 2 for a, p in zip(actuals, predictions, strict=True))
    return round(math.sqrt(total_sq / len(actuals)), 4)


def mean_bias_error(actuals: Sequence[float], predictions: Sequence[float]) -> float:
    """Calculate Mean Bias Error (MBE) in kW.

    MBE = (1 / n) * sum(predicted_i - actual_i)
    Positive indicates overall over-forecasting, negative indicates under-forecasting.
    """
    if len(actuals) != len(predictions):
        raise ValueError(
            f"Length mismatch: {len(actuals)} actuals vs {len(predictions)} predictions"
        )
    if not actuals:
        raise ValueError("Cannot calculate MBE on empty sequences")

    total = sum(p - a for a, p in zip(actuals, predictions, strict=True))
    return round(total / len(actuals), 4)


def safe_mape(
    actuals: Sequence[float],
    predictions: Sequence[float],
    threshold: float = 0.1,
) -> float | None:
    """Calculate Mean Absolute Percentage Error (MAPE) with zero-denominator safety.

    Only evaluates points where actual >= threshold (e.g., daylight intervals for solar).
    Returns None if no points satisfy the threshold.
    """
    if len(actuals) != len(predictions):
        raise ValueError(
            f"Length mismatch: {len(actuals)} actuals vs {len(predictions)} predictions"
        )

    valid_pairs = [(a, p) for a, p in zip(actuals, predictions, strict=True) if a >= threshold]

    if not valid_pairs:
        return None

    pct_errors = [abs(a - p) / a for a, p in valid_pairs]
    return round((sum(pct_errors) / len(valid_pairs)) * 100.0, 2)


def symmetric_mape(
    actuals: Sequence[float],
    predictions: Sequence[float],
    epsilon: float = 1e-5,
) -> float:
    """Calculate Symmetric Mean Absolute Percentage Error (sMAPE) in percent.

    sMAPE = (100% / n) * sum(
        2 * |actual_i - predicted_i| / (|actual_i| + |predicted_i| + epsilon)
    )
    Bounded between 0% and 200%. Handles zero actual and predicted safely.
    """
    if len(actuals) != len(predictions):
        raise ValueError(
            f"Length mismatch: {len(actuals)} actuals vs {len(predictions)} predictions"
        )
    if not actuals:
        raise ValueError("Cannot calculate sMAPE on empty sequences")

    total = 0.0
    for a, p in zip(actuals, predictions, strict=True):
        denom = abs(a) + abs(p) + epsilon
        total += (2.0 * abs(a - p)) / denom

    return round((total / len(actuals)) * 100.0, 2)


def normalized_mae(
    actuals: Sequence[float],
    predictions: Sequence[float],
    capacity_kw: float,
) -> float:
    """Calculate Normalized MAE (nMAE) as a percentage of installed asset capacity.

    nMAE = (MAE / capacity_kw) * 100%
    This is the standard CERC/CEA metric for renewable energy forecasting in India.
    """
    if capacity_kw <= 0:
        raise ValueError(f"Capacity must be positive, got {capacity_kw}")

    mae = mean_absolute_error(actuals, predictions)
    return round((mae / capacity_kw) * 100.0, 2)


def compute_all_metrics(
    actuals: Sequence[float],
    predictions: Sequence[float],
    capacity_kw: float | None = None,
    zero_threshold: float = 0.1,
) -> ForecastMetricsResult:
    """Compute comprehensive forecast metrics suite."""
    if len(actuals) != len(predictions):
        raise ValueError(
            f"Length mismatch: {len(actuals)} actuals vs {len(predictions)} predictions"
        )

    mae = mean_absolute_error(actuals, predictions)
    rmse = root_mean_squared_error(actuals, predictions)
    mbe = mean_bias_error(actuals, predictions)
    mape = safe_mape(actuals, predictions, threshold=zero_threshold)
    smape = symmetric_mape(actuals, predictions)
    nmae = normalized_mae(actuals, predictions, capacity_kw) if capacity_kw else None

    # Count how many intervals were evaluated for safe_mape vs total
    evaluated = sum(1 for a in actuals if a >= zero_threshold)
    skipped = len(actuals) - evaluated

    return ForecastMetricsResult(
        sample_count=len(actuals),
        mae_kw=mae,
        rmse_kw=rmse,
        mean_bias_kw=mbe,
        safe_mape_percent=mape,
        smape_percent=smape,
        nmae_percent=nmae,
        evaluated_intervals=evaluated,
        skipped_intervals=skipped,
    )
