"""Forecast orchestration.

    telemetry -> ForecastRequest -> ForecastProvider -> forecast_points -> surplus

Owns the transaction boundary for a forecast run (docs/04_DATA_MODEL.md) and
the sequencing around a provider. It contains **no forecasting algorithm**: it
gathers history, calls `provider.predict(...)`, validates the shape of what
comes back, and persists it. Which provider it holds is decided by
configuration or a caller — never hard-coded here, and never visible to market
code (docs/06_OPEN_SOURCE_INTEGRATION.md section 5).

A run row is written *before* the provider is invoked, so a provider that
raises still leaves a record saying a forecast was attempted, by whom, and why
it failed — an adapter failure stays observable rather than vanishing
(docs/01_FINAL_ARCHITECTURE.md).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models.forecasting import ForecastPoint, ForecastRun
from app.domain.enums import ForecastRunStatus, ForecastType
from app.domain.interfaces.forecasting import (
    ForecastProvider,
    ForecastRequest,
    ForecastResult,
    HistoricalObservation,
)
from app.domain.policies.surplus import SurplusWindow, calculate_surplus
from app.repositories import (
    ForecastPointRepository,
    ForecastRunRepository,
    SiteRepository,
    TelemetryRepository,
)

# How much past telemetry is handed to a provider by default. Two weeks covers
# a fortnight of daily solar and load cycles, which is the shortest span that
# lets a naive model see both weekday and weekend behaviour. It is a parameter,
# never read from a global.
DEFAULT_HISTORY_WINDOW = timedelta(days=14)

# Default bucket width of a forecast horizon: one CEA AMI metering block
# (docs/11_REGULATORY_AND_INDIA_CONTEXT.md), matching how telemetry arrives.
DEFAULT_INTERVAL = timedelta(minutes=15)


class ForecastProviderError(UnprocessableError):
    """A provider failed or returned something the contract does not allow."""

    code = "FORECAST_PROVIDER_FAILED"


def run_forecast(
    session: Session,
    *,
    site_id: UUID,
    forecast_type: ForecastType,
    provider: ForecastProvider,
    horizon_start: datetime,
    horizon_end: datetime,
    interval: timedelta = DEFAULT_INTERVAL,
    history_window: timedelta = DEFAULT_HISTORY_WINDOW,
    at: datetime | None = None,
) -> ForecastRun:
    """Execute one forecast and persist it.

    The provider is passed in rather than looked up, so this function stays
    ignorant of which implementation exists. `app.services.forecast_registry`
    is what turns configuration into a provider instance.
    """
    _require_site(session, site_id)
    _validate_horizon(horizon_start, horizon_end, interval)

    if not provider.supports(forecast_type):
        raise ForecastProviderError(
            f"Provider {provider.name!r} does not produce {forecast_type.value} forecasts.",
            code="FORECAST_TYPE_UNSUPPORTED",
            details={"provider": provider.name, "forecast_type": forecast_type.value},
        )

    # `created_at` is the *generation* timestamp — when the prediction was
    # made — as distinct from the points' intervals, which are when the
    # predicted energy flows. Settable so a caller (or a test) can pin it and
    # make "the newest forecast for this interval" deterministic.
    run = ForecastRun(
        forecast_type=forecast_type,
        provider=provider.name,
        model_version=provider.model_version,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        status=ForecastRunStatus.RUNNING,
        created_at=at or datetime.now(UTC),
    )
    ForecastRunRepository(session).add(run)
    # Committed before the provider runs, so the attempt survives a provider
    # that raises, hangs or takes the process down with it.
    session.commit()

    request = ForecastRequest(
        site_id=site_id,
        forecast_type=forecast_type,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        interval=interval,
        history=gather_history(session, site_id, end=horizon_start, window=history_window),
    )

    try:
        result = provider.predict(request)
        _validate_result(result, request, provider)
    except ForecastProviderError:
        _mark_failed(session, run, "provider returned an invalid result")
        raise
    except Exception as exc:
        _mark_failed(session, run, f"{exc.__class__.__name__}: {exc}")
        raise ForecastProviderError(
            f"Provider {provider.name!r} failed to produce a forecast.",
            details={"provider": provider.name, "reason": exc.__class__.__name__},
        ) from exc

    ForecastPointRepository(session).add_all(
        [
            ForecastPoint(
                forecast_run_id=run.id,
                site_id=site_id,
                interval_start=point.interval_start,
                interval_end=point.interval_end,
                predicted_kw=point.predicted_kw,
                predicted_kwh=point.predicted_kwh,
                confidence=point.confidence,
                lower_bound=point.lower_bound,
                upper_bound=point.upper_bound,
            )
            for point in result.points
        ]
    )
    run.status = ForecastRunStatus.COMPLETED
    # A provider may report a more specific version than it advertises.
    run.model_version = result.model_version
    session.commit()
    session.refresh(run)
    return run


def gather_history(
    session: Session,
    site_id: UUID,
    *,
    end: datetime,
    window: timedelta = DEFAULT_HISTORY_WINDOW,
) -> tuple[HistoricalObservation, ...]:
    """Site-level telemetry history, oldest first.

    Only usable readings are passed to a provider: a stale or invalid reading
    is not an observation of what happened, and fitting a model to data the
    platform itself does not trust would launder that distrust into a forecast.

    Readings from several meters covering the same interval are summed, because
    a forecast is about the site, not about one meter.
    """
    rows = TelemetryRepository(session).list_for_site(
        site_id, start=end - window, end=end, only_valid=True, limit=100_000
    )

    buckets: dict[datetime, _HistoryBucket] = {}
    for row in rows:
        bucket = buckets.get(row.interval_start)
        if bucket is None:
            bucket = _HistoryBucket(interval_end=row.interval_end)
            buckets[row.interval_start] = bucket
        bucket.add(row.generation_kw, row.load_kw, row.energy_kwh)

    return tuple(
        HistoricalObservation(
            interval_start=start,
            interval_end=bucket.interval_end,
            generation_kw=bucket.generation_kw,
            load_kw=bucket.load_kw,
            energy_kwh=bucket.energy_kwh,
        )
        for start, bucket in sorted(buckets.items())
    )


@dataclass
class _HistoryBucket:
    """One interval's readings, summed across a site's meters.

    `None` is preserved rather than coerced to zero: a channel no meter
    measured stays unmeasured, exactly as in telemetry.
    """

    interval_end: datetime
    generation_kw: Decimal | None = None
    load_kw: Decimal | None = None
    energy_kwh: Decimal | None = None

    def add(
        self,
        generation_kw: Decimal | None,
        load_kw: Decimal | None,
        energy_kwh: Decimal | None,
    ) -> None:
        self.generation_kw = _accumulate(self.generation_kw, generation_kw)
        self.load_kw = _accumulate(self.load_kw, load_kw)
        self.energy_kwh = _accumulate(self.energy_kwh, energy_kwh)


def _accumulate(total: Decimal | None, value: Decimal | None) -> Decimal | None:
    if value is None:
        return total
    return value if total is None else total + value


def get_run(session: Session, run_id: UUID) -> ForecastRun:
    run = ForecastRunRepository(session).get(run_id)
    if run is None:
        raise NotFoundError(
            "Forecast run not found.",
            code="FORECAST_RUN_NOT_FOUND",
            details={"id": str(run_id)},
        )
    return run


def get_points_for_site(
    session: Session,
    site_id: UUID,
    *,
    start: datetime,
    end: datetime,
    forecast_type: ForecastType | None = None,
) -> Sequence[ForecastPoint]:
    """Forecast points for a site over a window, from completed runs only."""
    _require_site(session, site_id)
    return ForecastPointRepository(session).list_for_site(
        site_id, start=start, end=end, forecast_type=forecast_type
    )


def get_surplus_for_site(
    session: Session, site_id: UUID, *, start: datetime, end: datetime
) -> SurplusWindow:
    """Expected surplus for a site over a window.

    Pairs the newest solar forecast with the newest load forecast and hands
    both to `app.domain.policies.surplus`. No arithmetic happens here: the rule
    lives in the policy so it stays independently testable and cannot drift
    when the provider changes.
    """
    _require_site(session, site_id)
    points = ForecastPointRepository(session)

    generation = points.latest_per_interval_for_site(
        site_id, start=start, end=end, forecast_type=ForecastType.SOLAR
    )
    consumption = points.latest_per_interval_for_site(
        site_id, start=start, end=end, forecast_type=ForecastType.LOAD
    )

    return calculate_surplus(
        generation=[(p.interval_start, p.interval_end, p.predicted_kw) for p in generation],
        consumption=[(p.interval_start, p.interval_end, p.predicted_kw) for p in consumption],
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _validate_horizon(start: datetime, end: datetime, interval: timedelta) -> None:
    if end <= start:
        raise UnprocessableError(
            "horizon_end must be after horizon_start.",
            code="FORECAST_HORIZON_INVALID",
        )
    if interval <= timedelta(0):
        raise UnprocessableError(
            "interval must be greater than zero.", code="FORECAST_INTERVAL_INVALID"
        )


def _validate_result(
    result: ForecastResult, request: ForecastRequest, provider: ForecastProvider
) -> None:
    """Check a provider's output before trusting it.

    The contract is enforced at the boundary rather than assumed, so a
    misbehaving provider produces a clear, attributable error instead of
    silently poisoning the forecast store.
    """
    if result.forecast_type is not request.forecast_type:
        raise ForecastProviderError(
            "Provider returned a different forecast type than requested.",
            details={
                "requested": request.forecast_type.value,
                "returned": result.forecast_type.value,
            },
        )
    if not result.points:
        raise ForecastProviderError(
            f"Provider {provider.name!r} returned no forecast points.",
            details={"provider": provider.name},
        )

    seen: set[datetime] = set()
    for point in result.points:
        if point.interval_end <= point.interval_start:
            raise ForecastProviderError(
                "Provider returned a point whose interval_end is not after interval_start.",
                details={"interval_start": point.interval_start.isoformat()},
            )
        if point.interval_start in seen:
            raise ForecastProviderError(
                "Provider returned duplicate points for the same interval.",
                details={"interval_start": point.interval_start.isoformat()},
            )
        seen.add(point.interval_start)

        if not (request.horizon_start <= point.interval_start < request.horizon_end):
            raise ForecastProviderError(
                "Provider returned a point outside the requested horizon.",
                details={
                    "interval_start": point.interval_start.isoformat(),
                    "horizon_start": request.horizon_start.isoformat(),
                    "horizon_end": request.horizon_end.isoformat(),
                },
            )
        if point.confidence is not None and not (Decimal("0") <= point.confidence <= Decimal("1")):
            raise ForecastProviderError(
                "Provider returned a confidence outside [0, 1].",
                details={"confidence": str(point.confidence)},
            )


def _mark_failed(session: Session, run: ForecastRun, reason: str) -> None:
    """Record why a run failed, and commit that fact.

    No rollback first: a provider is pure by contract, so nothing of its doing
    is pending on this session, and the run row was committed before it was
    called. Rolling back here would discard the very record this function
    exists to preserve.
    """
    run.status = ForecastRunStatus.FAILED
    run.error = reason[:500]
    session.commit()


def _require_site(session: Session, site_id: UUID) -> None:
    if SiteRepository(session).get(site_id) is None:
        raise NotFoundError("Site not found.", code="SITE_NOT_FOUND", details={"id": str(site_id)})
