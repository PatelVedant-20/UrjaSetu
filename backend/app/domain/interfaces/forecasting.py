"""The forecasting contract.

This is the stable boundary between the platform and whatever algorithm
produces a forecast:

    telemetry -> ForecastRequest -> ForecastProvider -> ForecastResult
    -> forecast_points -> surplus

Nothing here knows how a prediction is made. A naive baseline, XGBoost,
LightGBM, an OpenSTEF-backed provider or a hosted model all satisfy the same
Protocol, so the provider can be replaced without touching the orchestration
service, the persistence layer or any market code
(docs/06_OPEN_SOURCE_INTEGRATION.md section 5).

A provider is **pure**: it receives the history it needs in the request and
returns a result. It never opens a session, reads a model, or writes a row.
That is what makes a forecast reproducible from stored inputs
(docs/00_PROJECT_BIBLE.md: traceability) and testable without PostgreSQL.

Units follow docs/00_PROJECT_BIBLE.md section 6 — power in kW, energy in kWh,
timestamps timezone-aware UTC — and are never converted here.

Two timestamps are deliberately distinct and must not be confused:

* `interval_start` / `interval_end` — **when the predicted energy flows**.
* `generated_at` — **when the prediction was made**. Two runs over the same
  horizon differ only in this field, which is what makes a forecast auditable
  after the fact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.enums import ForecastType


@dataclass(frozen=True, slots=True)
class HistoricalObservation:
    """One past interval, as input to a forecast.

    Deliberately not `app.domain.interfaces.telemetry.NormalizedReading`: that
    contract is meter-scoped and carries ingestion concerns (`source`,
    `source_unavailable`) a forecaster has no use for. This is the site-level
    view — what was generated and consumed over an interval — so the
    forecasting layer does not inherit telemetry's shape.

    `None` means the channel was not measured, exactly as in telemetry. A
    provider must not read it as zero.
    """

    interval_start: datetime
    interval_end: datetime
    generation_kw: Decimal | None = None
    load_kw: Decimal | None = None
    energy_kwh: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    """Everything a provider needs to produce a forecast.

    Self-contained on purpose: a provider given the same request must return
    the same result, so a request can be logged and replayed to explain a
    forecast later.
    """

    site_id: UUID
    forecast_type: ForecastType
    horizon_start: datetime
    horizon_end: datetime
    # Bucket width of the requested points, e.g. 15 minutes.
    interval: timedelta
    # Oldest first. May be empty: a provider must decide for itself whether it
    # can forecast a site with no history, rather than the service guessing.
    history: Sequence[HistoricalObservation] = field(default_factory=tuple)

    @property
    def expected_point_count(self) -> int:
        """How many buckets the horizon divides into.

        The service checks a provider's output against this rather than
        trusting it, so a provider that returns a short or ragged horizon is
        caught at the boundary.
        """
        span = self.horizon_end - self.horizon_start
        if self.interval <= timedelta(0) or span <= timedelta(0):
            return 0
        return int(span / self.interval)


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """One predicted bucket.

    Mirrors the stored columns of docs/04_DATA_MODEL.md entity 12. `confidence`
    and the bounds are optional because not every provider is probabilistic —
    a naive baseline has no meaningful uncertainty, and inventing one would be
    worse than reporting none.
    """

    interval_start: datetime
    interval_end: datetime
    predicted_kw: Decimal | None = None
    predicted_kwh: Decimal | None = None
    confidence: Decimal | None = None
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """What a provider returns.

    `provider` and `model_version` identify *what produced this*, and are
    persisted on the run so a stored forecast can always be attributed to a
    specific implementation at a specific version.
    """

    forecast_type: ForecastType
    provider: str
    model_version: str
    generated_at: datetime
    points: Sequence[ForecastPoint] = field(default_factory=tuple)


class ForecastProvider(Protocol):
    """What a forecasting implementation must provide.

    Implementations live in `app/adapters/forecast/` and are owned by the agent
    assigned that adapter. This declaration is the contract they implement, not
    an implementation.

    Deliberately tiny: one identity pair and one pure method. Anything a
    provider needs beyond that — weather, model artefacts, tuning — is its own
    constructor's business, invisible to the service.
    """

    @property
    def name(self) -> str:
        """Stable identifier, persisted as `forecast_runs.provider`."""
        ...

    @property
    def model_version(self) -> str:
        """Version of the model or algorithm, persisted alongside `name`.

        Change it whenever output could change for the same input, so a stored
        forecast stays explainable.
        """
        ...

    def supports(self, forecast_type: ForecastType) -> bool:
        """Whether this provider can produce that kind of forecast.

        Lets the service refuse a mismatch with a clear error instead of
        letting a provider improvise.
        """
        ...

    def predict(self, request: ForecastRequest) -> ForecastResult:
        """Produce a forecast for the request.

        Must be deterministic: the same request yields the same result. Any
        randomness must be explicitly seeded from the request
        (docs/10_TESTING_AND_INTEGRATION.md).

        Raise on failure rather than returning an empty or partial result — the
        service records the run as failed and surfaces a typed error, so a
        broken provider is visible instead of silently producing nothing.
        """
        ...
