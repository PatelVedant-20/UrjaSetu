"""Baseline forecast provider.

A deterministic Same-Period Historical Average (diurnal baseline): every future
interval is predicted from what this site did at the same time of day in its
recent history.

It implements `app.domain.interfaces.forecasting.ForecastProvider` and defines
**no contract types of its own** — the request, result and point types all come
from the domain. That is what lets it be swapped for XGBoost, LightGBM or an
OpenSTEF-backed provider without the forecasting service noticing
(docs/06_OPEN_SOURCE_INTEGRATION.md section 5).

Pure by contract: no session, no I/O, no clock. The same request always yields
the same result (docs/10_TESTING_AND_INTEGRATION.md: determinism).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.enums import ForecastType
from app.domain.interfaces.forecasting import (
    ForecastPoint,
    ForecastRequest,
    ForecastResult,
    HistoricalObservation,
)

ZERO = Decimal("0")

# Providers are configured through their constructor, never through the
# request: the request is the domain's contract and must stay identical for
# every provider.
DEFAULT_NAME = "baseline"
DEFAULT_MODEL_VERSION = "1.0.0"
DEFAULT_REFERENCE_DAYS = 7


class BaselineForecastProvider:
    """Same-period historical average.

    Groups history by time of day, then predicts each future interval as the
    mean of the samples that share its (hour, minute). Uncertainty is the
    sample standard deviation, which is real information rather than an
    invented confidence.
    """

    def __init__(
        self,
        *,
        name: str = DEFAULT_NAME,
        model_version: str = DEFAULT_MODEL_VERSION,
        reference_days: int = DEFAULT_REFERENCE_DAYS,
        min_required_samples: int = 0,
        pv_capacity_kw: Decimal | None = None,
    ) -> None:
        self._name = name
        self._model_version = model_version
        self._reference_days = max(1, reference_days)
        self._min_required_samples = max(0, min_required_samples)
        # Optional physical ceiling: a site cannot generate more than its
        # inverter is rated for, however sunny the history was.
        self._pv_capacity_kw = pv_capacity_kw

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return self._model_version

    def supports(self, forecast_type: ForecastType) -> bool:
        """Solar and load only.

        `SURPLUS` is deliberately unsupported: surplus is derived from a solar
        and a load forecast by `app.domain.policies.surplus`, so that the rule
        stays a reviewable business decision rather than something buried in a
        model.
        """
        return forecast_type in (ForecastType.SOLAR, ForecastType.LOAD)

    def predict(self, request: ForecastRequest) -> ForecastResult:
        """Produce a forecast for the requested horizon."""
        samples = self._group_by_time_of_day(request)

        total = sum(len(v) for v in samples.values())
        if total < self._min_required_samples:
            raise ValueError(
                f"History contains {total} usable measurements, "
                f"but at least {self._min_required_samples} are required."
            )

        points: list[ForecastPoint] = []
        start = _as_utc(request.horizon_start)
        horizon_end = _as_utc(request.horizon_end)

        while start < horizon_end:
            end = min(start + request.interval, horizon_end)
            points.append(
                self._point_for(
                    start,
                    end,
                    samples.get((start.hour, start.minute), []),
                    Decimal(str((end - start).total_seconds())) / Decimal(3600),
                )
            )
            start = end

        return ForecastResult(
            forecast_type=request.forecast_type,
            provider=self._name,
            model_version=self._model_version,
            # The instant the prediction was made, as distinct from the
            # intervals it predicts. Derived from the request so the provider
            # stays free of clock reads and therefore deterministic.
            generated_at=_as_utc(request.horizon_start),
            points=points,
        )

    # -- internals --------------------------------------------------------

    def _group_by_time_of_day(
        self, request: ForecastRequest
    ) -> dict[tuple[int, int], list[Decimal]]:
        """Bucket the history by (hour, minute) of its interval start.

        Only the channel matching the requested forecast type is read; an
        unmeasured channel contributes nothing rather than being read as zero.
        """
        grouped: dict[tuple[int, int], list[Decimal]] = defaultdict(list)
        for observation in request.history:
            value = _channel(observation, request.forecast_type)
            if value is None:
                continue
            moment = _as_utc(observation.interval_start)
            grouped[(moment.hour, moment.minute)].append(value)
        return grouped

    def _point_for(
        self,
        interval_start: datetime,
        interval_end: datetime,
        samples: list[Decimal],
        hours: Decimal,
    ) -> ForecastPoint:
        if not samples:
            # Nothing was ever observed at this time of day. Reporting zero
            # with zero confidence says "no expectation", which the surplus
            # policy and the market can both reason about.
            return ForecastPoint(
                interval_start=interval_start,
                interval_end=interval_end,
                predicted_kw=ZERO,
                predicted_kwh=ZERO,
                confidence=ZERO,
                lower_bound=ZERO,
                upper_bound=ZERO,
            )

        count = len(samples)
        mean = max(ZERO, sum(samples, ZERO) / Decimal(count))
        mean = self._cap(mean)

        if count > 1:
            variance = sum(((s - mean) ** 2 for s in samples), ZERO) / Decimal(count - 1)
            deviation = Decimal(str(math.sqrt(float(variance))))
        else:
            deviation = ZERO

        lower = max(ZERO, mean - deviation).quantize(Decimal("0.001"))
        upper = self._cap(mean + deviation).quantize(Decimal("0.001"))

        # More samples and steadier ones mean more confidence. A heuristic, and
        # labelled as one — it is not a calibrated probability.
        sample_factor = min(1.0, count / self._reference_days)
        stability = 1.0 / (1.0 + float(deviation) / (float(mean) + 1.0))
        confidence = Decimal(str(round(sample_factor * stability, 3)))
        confidence = max(Decimal("0.05"), min(Decimal("1.0"), confidence))

        predicted_kw = mean.quantize(Decimal("0.001"))
        return ForecastPoint(
            interval_start=interval_start,
            interval_end=interval_end,
            predicted_kw=predicted_kw,
            predicted_kwh=(predicted_kw * hours).quantize(Decimal("0.001")),
            confidence=confidence,
            lower_bound=lower,
            upper_bound=upper,
        )

    def _cap(self, value: Decimal) -> Decimal:
        if self._pv_capacity_kw is None:
            return value
        return min(value, self._pv_capacity_kw)


def _channel(observation: HistoricalObservation, forecast_type: ForecastType) -> Decimal | None:
    """The observed channel a forecast type is about."""
    if forecast_type is ForecastType.SOLAR:
        return observation.generation_kw
    if forecast_type is ForecastType.LOAD:
        return observation.load_kw
    if forecast_type is ForecastType.SURPLUS:
        generation = observation.generation_kw
        load = observation.load_kw
        if generation is None or load is None:
            return None
        return max(ZERO, generation - load)
    return None


def _as_utc(moment: datetime) -> datetime:
    """Normalise to timezone-aware UTC (docs/00_PROJECT_BIBLE.md section 6)."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


__all__ = ["BaselineForecastProvider"]
