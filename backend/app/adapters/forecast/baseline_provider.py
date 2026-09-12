"""Baseline Forecast Provider for UrjaSetu.

Implements a deterministic Same-Period Historical Average (Diurnal Baseline)
forecasting provider conforming to docs/00_PROJECT_BIBLE.md, docs/04_DATA_MODEL.md
entities 11 & 12, and docs/07_CODING_PHASES.md Phase 3 requirements.

MATHEMATICAL DEFINITION:
------------------------
For each forecast interval [t_start, t_end) in the target horizon:
1. Extract the time-of-day key: (hour, minute) of t_start.
2. Select all valid historical readings matching the same (hour, minute).
3. Compute the arithmetic mean of the target channel:
       P_pred = (1 / N) * sum(P_i)  for valid readings i in 1..N
4. Compute standard deviation:
       sigma = sqrt((1 / N) * sum((P_i - P_pred)^2))
5. Derive bounds and energy:
       lower_bound = max(0.0, P_pred - sigma)
       upper_bound = P_pred + sigma  (capped at pv_capacity_kw if solar)
       predicted_kwh = P_pred * (interval_minutes / 60.0)
6. Derive confidence score [0.0, 1.0]:
       confidence = min(1.0, N / N_ref) * (1.0 / (1.0 + sigma / (P_pred + 1.0)))

DETERMINISM & INDEPENDENCE:
---------------------------
- 100% deterministic: identical history and horizon produce identical results.
- Zero external AI/cloud APIs, zero deep learning libraries.
- Decoupled from PostgreSQL: consumes in-memory NormalizedReading records.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from app.domain.interfaces.telemetry import NormalizedReading


class ForecastProviderError(Exception):
    """Base exception for forecast provider errors."""


class InvalidHorizonError(ForecastProviderError):
    """Raised when horizon_start >= horizon_end or horizon parameters are invalid."""


class InsufficientHistoryError(ForecastProviderError):
    """Raised when historical readings are insufficient to generate a forecast."""


ForecastType = Literal["solar", "load", "surplus"]


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """One forecast interval output point.

    Matches entity 12 `forecast_points` in docs/04_DATA_MODEL.md.
    """

    interval_start: datetime
    interval_end: datetime
    predicted_kw: Decimal
    predicted_kwh: Decimal
    confidence: Decimal
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None

    def __post_init__(self) -> None:
        if self.interval_end <= self.interval_start:
            raise ValueError(
                f"interval_end ({self.interval_end}) must be strictly after "
                f"interval_start ({self.interval_start})"
            )
        if self.predicted_kw < Decimal("0.0"):
            raise ValueError(f"predicted_kw cannot be negative: {self.predicted_kw}")
        if self.predicted_kwh < Decimal("0.0"):
            raise ValueError(f"predicted_kwh cannot be negative: {self.predicted_kwh}")
        if not (Decimal("0.0") <= self.confidence <= Decimal("1.0")):
            raise ValueError(f"confidence must be in [0.0, 1.0], got: {self.confidence}")


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    """Forecast generation request passed to the provider."""

    site_id: UUID
    forecast_type: ForecastType
    horizon_start: datetime
    horizon_end: datetime
    history: Sequence[NormalizedReading]
    interval_minutes: int = 15
    pv_capacity_kw: Decimal | None = None
    min_required_samples: int = 1

    def __post_init__(self) -> None:
        if self.horizon_end <= self.horizon_start:
            raise InvalidHorizonError(
                f"horizon_end ({self.horizon_end}) must be after "
                f"horizon_start ({self.horizon_start})"
            )
        if self.interval_minutes <= 0:
            raise InvalidHorizonError(
                f"interval_minutes must be positive, got {self.interval_minutes}"
            )


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """Forecast result output returned by the provider."""

    site_id: UUID
    forecast_type: ForecastType
    provider: str
    model_version: str
    horizon_start: datetime
    horizon_end: datetime
    points: list[ForecastPoint] = field(default_factory=list)

    @property
    def total_predicted_kwh(self) -> Decimal:
        return sum((p.predicted_kwh for p in self.points), start=Decimal("0.0"))

    @property
    def average_confidence(self) -> Decimal:
        if not self.points:
            return Decimal("0.0")
        total_conf = sum((p.confidence for p in self.points), start=Decimal("0.0"))
        return (total_conf / Decimal(len(self.points))).quantize(Decimal("0.001"))


@runtime_checkable
class ForecastProvider(Protocol):
    """Protocol that all forecasting providers must implement."""

    @property
    def provider_id(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    def generate_forecast(self, request: ForecastRequest) -> ForecastResult: ...


class SamePeriodAverageForecastProvider:
    """Same-Period Historical Average (Diurnal Baseline) Forecast Provider.

    Calculates future intervals based on historical time-of-day averages.
    """

    def __init__(
        self,
        provider_id: str = "baseline_same_period_average",
        model_version: str = "0.1.0",
        reference_days: int = 7,
    ) -> None:
        self._provider_id = provider_id
        self._model_version = model_version
        self._reference_days = max(1, reference_days)

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_version(self) -> str:
        return self._model_version

    def generate_forecast(self, request: ForecastRequest) -> ForecastResult:
        """Generate a deterministic baseline forecast for the requested horizon."""
        horizon_start = self._ensure_utc(request.horizon_start)
        horizon_end = self._ensure_utc(request.horizon_end)
        interval_delta = timedelta(minutes=request.interval_minutes)

        # 1. Group valid historical readings by (hour, minute) of interval_start
        tod_samples: dict[tuple[int, int], list[Decimal]] = defaultdict(list)
        for r in request.history:
            if r.source_unavailable:
                continue

            r_start = self._ensure_utc(r.interval_start)
            tod_key = (r_start.hour, r_start.minute)

            val = self._extract_channel_value(r, request.forecast_type)
            if val is not None:
                tod_samples[tod_key].append(val)

        # 2. Check minimal data requirements if specified
        total_valid_samples = sum(len(samples) for samples in tod_samples.values())
        if total_valid_samples < request.min_required_samples:
            raise InsufficientHistoryError(
                f"History contains {total_valid_samples} valid measurements, but minimum "
                f"required is {request.min_required_samples}"
            )

        # 3. Iterate over the horizon intervals
        points: list[ForecastPoint] = []
        current_interval_start = horizon_start
        hours_ratio = Decimal(str(request.interval_minutes / 60.0))

        while current_interval_start < horizon_end:
            current_interval_end = min(current_interval_start + interval_delta, horizon_end)
            tod_key = (current_interval_start.hour, current_interval_start.minute)

            samples = tod_samples.get(tod_key, [])

            if samples:
                # Compute arithmetic mean
                n = len(samples)
                mean_val = sum(samples, start=Decimal("0.0")) / Decimal(n)
                mean_kw = max(Decimal("0.0"), mean_val)

                # Cap solar generation at rated capacity if provided
                if request.forecast_type == "solar" and request.pv_capacity_kw is not None:
                    mean_kw = min(mean_kw, request.pv_capacity_kw)

                # Compute sample standard deviation
                if n > 1:
                    variance = sum(
                        ((s - mean_kw) ** 2 for s in samples), start=Decimal("0.0")
                    ) / Decimal(n - 1)
                    std_dev = Decimal(str(math.sqrt(float(variance))))
                else:
                    std_dev = Decimal("0.0")

                # Bounds
                lower_bound = max(Decimal("0.0"), mean_kw - std_dev).quantize(Decimal("0.001"))
                upper_bound = (mean_kw + std_dev).quantize(Decimal("0.001"))
                if request.forecast_type == "solar" and request.pv_capacity_kw is not None:
                    upper_bound = min(upper_bound, request.pv_capacity_kw)

                # Confidence heuristic based on sample sufficiency and stability
                sample_factor = min(1.0, n / self._reference_days)
                stability_factor = 1.0 / (1.0 + float(std_dev) / (float(mean_kw) + 1.0))
                confidence_score = Decimal(str(round(sample_factor * stability_factor, 3)))
                confidence_score = max(Decimal("0.05"), min(Decimal("1.0"), confidence_score))

                pred_kw = mean_kw.quantize(Decimal("0.001"))
                pred_kwh = (pred_kw * hours_ratio).quantize(Decimal("0.001"))
            else:
                # No historical data for this time of day (e.g. sparse history)
                pred_kw = Decimal("0.0")
                pred_kwh = Decimal("0.0")
                confidence_score = Decimal("0.0")
                lower_bound = Decimal("0.0")
                upper_bound = Decimal("0.0")

            point = ForecastPoint(
                interval_start=current_interval_start,
                interval_end=current_interval_end,
                predicted_kw=pred_kw,
                predicted_kwh=pred_kwh,
                confidence=confidence_score,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )
            points.append(point)
            current_interval_start = current_interval_end

        return ForecastResult(
            site_id=request.site_id,
            forecast_type=request.forecast_type,
            provider=self._provider_id,
            model_version=self._model_version,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            points=points,
        )

    @staticmethod
    def _extract_channel_value(
        reading: NormalizedReading,
        forecast_type: ForecastType,
    ) -> Decimal | None:
        """Extract the numeric power channel corresponding to the forecast type."""
        if forecast_type == "solar":
            return reading.generation_kw
        if forecast_type == "load":
            return reading.load_kw
        if forecast_type == "surplus":
            gen = reading.generation_kw or Decimal("0.0")
            load = reading.load_kw or Decimal("0.0")
            return max(Decimal("0.0"), gen - load)
        return None

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        """Ensure a datetime is timezone-aware UTC."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
