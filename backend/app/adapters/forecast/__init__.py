"""UrjaSetu Forecast Adapters.

Provides pluggable forecasting provider implementations conforming to
the ForecastProvider protocol.
"""

from __future__ import annotations

from app.adapters.forecast.baseline_provider import (
    ForecastPoint,
    ForecastProvider,
    ForecastProviderError,
    ForecastRequest,
    ForecastResult,
    ForecastType,
    InsufficientHistoryError,
    InvalidHorizonError,
    SamePeriodAverageForecastProvider,
)

__all__ = [
    "ForecastPoint",
    "ForecastProvider",
    "ForecastProviderError",
    "ForecastRequest",
    "ForecastResult",
    "ForecastType",
    "InsufficientHistoryError",
    "InvalidHorizonError",
    "SamePeriodAverageForecastProvider",
]
