"""API contracts for the Forecasting resource group (docs/05_API_SPEC.md).

Transport-layer models only. These are **not** the domain contract: the domain
speaks `app.domain.interfaces.forecasting` dataclasses, and conversion between
the two is explicit and one-directional (`to_*` methods here, `model_validate`
on the way out). A Pydantic model must never become the thing providers
implement against, or the transport layer would start dictating the domain.

Field names, units and enum values come from docs/04_DATA_MODEL.md entities 11
and 12; nothing here is invented.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import ForecastRunStatus, ForecastType

# One CEA AMI metering block, matching how telemetry arrives
# (docs/11_REGULATORY_AND_INDIA_CONTEXT.md).
DEFAULT_INTERVAL_MINUTES = 15


class ForecastRunCreate(BaseModel):
    """`POST /forecasts/runs` request body."""

    site_id: UUID
    forecast_type: ForecastType
    horizon_start: datetime
    horizon_end: datetime
    interval_minutes: int = Field(default=DEFAULT_INTERVAL_MINUTES, gt=0, le=1440)
    # Optional: omitted means the configured default provider. Named here so a
    # caller can pin a provider without the router knowing any provider exists.
    provider: str | None = None

    @model_validator(mode="after")
    def _check_horizon(self) -> ForecastRunCreate:
        if self.horizon_end <= self.horizon_start:
            raise ValueError("horizon_end must be after horizon_start")
        return self

    def to_interval(self) -> timedelta:
        """Explicit conversion into the domain's unit."""
        return timedelta(minutes=self.interval_minutes)


class ForecastPointRead(BaseModel):
    """One predicted bucket, as stored."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    forecast_run_id: UUID
    site_id: UUID
    interval_start: datetime
    interval_end: datetime
    predicted_kw: Decimal | None
    predicted_kwh: Decimal | None
    confidence: Decimal | None
    lower_bound: Decimal | None
    upper_bound: Decimal | None


class ForecastRunRead(BaseModel):
    """`POST /forecasts/runs` and `GET /forecasts/runs/{run_id}` response.

    `created_at` is the *generation* timestamp — when the prediction was made —
    as distinct from the points' intervals, which say when the predicted energy
    flows.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    forecast_type: ForecastType
    provider: str
    model_version: str
    horizon_start: datetime
    horizon_end: datetime
    status: ForecastRunStatus
    error: str | None
    created_at: datetime
    updated_at: datetime


class ForecastSeriesRead(BaseModel):
    """`GET /sites/{site_id}/forecasts` response."""

    site_id: UUID
    start: datetime
    end: datetime
    count: int
    points: list[ForecastPointRead] = Field(default_factory=list)


class SurplusPointRead(BaseModel):
    """Expected surplus over one interval.

    `surplus_kw` is signed — a negative value is an expected deficit, which the
    market needs in order to size buy orders. `exportable_kw` is the clamped
    view: what could actually be offered.
    """

    interval_start: datetime
    interval_end: datetime
    generation_kw: Decimal | None
    load_kw: Decimal | None
    surplus_kw: Decimal | None
    exportable_kw: Decimal


class SurplusRead(BaseModel):
    """`GET /sites/{site_id}/surplus` response."""

    site_id: UUID
    start: datetime
    end: datetime
    total_exportable_kwh: Decimal
    has_exportable_energy: bool
    points: list[SurplusPointRead] = Field(default_factory=list)
