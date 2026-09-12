"""API contracts for the Telemetry resource group (docs/05_API_SPEC.md).

Transport-layer models only — no SQL and no quality rules
(docs/03_REPOSITORY_STRUCTURE.md). Field names, units and enum values come from
docs/04_DATA_MODEL.md entity 10; nothing here is invented.

Validation split, deliberately:

* This layer rejects input that is malformed as *a request* — a missing
  `meter_id`, an unparseable timestamp, a negative power value, a state of
  charge outside 0-100. Those get 422, because a caller can fix them.
* `app.domain.policies.telemetry_quality` classifies input that is well-formed
  but *questionable* — stale, out of order, duplicate. Those are recorded with
  a quality status, because an adapter replaying a CSV cannot fix them and the
  gap must stay visible.

The two do not overlap: the schema never assigns a quality status, and the
classifier never rejects a request.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import TelemetryQualityStatus, TelemetrySource
from app.domain.interfaces.telemetry import NormalizedReading

# Power and energy are magnitudes on a defined direction (import and export are
# separate channels), so none of them may be negative.
_NON_NEGATIVE = Field(default=None, ge=0)


class TelemetryReadingCreate(BaseModel):
    """`POST /telemetry/readings` request body.

    Unknown keys are ignored rather than rejected, so a caller may send context
    it finds useful (a `site_id`, say) without the API pretending to store it.
    A reading's site is derived from its meter; docs/04_DATA_MODEL.md puts no
    `site_id` on this table.
    """

    model_config = ConfigDict(extra="ignore")

    meter_id: UUID
    timestamp: datetime
    source: TelemetrySource

    energy_asset_id: UUID | None = None

    # Optional: an omitted interval is treated as an instantaneous sample.
    interval_start: datetime | None = None
    interval_end: datetime | None = None

    generation_kw: Decimal | None = _NON_NEGATIVE
    load_kw: Decimal | None = _NON_NEGATIVE
    grid_import_kw: Decimal | None = _NON_NEGATIVE
    grid_export_kw: Decimal | None = _NON_NEGATIVE
    energy_kwh: Decimal | None = _NON_NEGATIVE
    battery_soc: Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _check_interval(self) -> TelemetryReadingCreate:
        if (
            self.interval_start is not None
            and self.interval_end is not None
            and self.interval_end < self.interval_start
        ):
            raise ValueError("interval_end must not precede interval_start")
        return self

    def to_normalized(self) -> NormalizedReading:
        """Convert to the canonical domain contract.

        When the caller supplies no interval, the reading is recorded as an
        instantaneous sample — `interval_start == interval_end == timestamp`.
        No duration is invented: docs/00_PROJECT_BIBLE.md section 6 requires
        intervals to be explicit, so a caller who means a 15-minute block must
        say so.
        """
        start = self.interval_start if self.interval_start is not None else self.timestamp
        end = self.interval_end if self.interval_end is not None else start

        return NormalizedReading(
            meter_id=self.meter_id,
            energy_asset_id=self.energy_asset_id,
            timestamp=self.timestamp,
            interval_start=start,
            interval_end=end,
            source=self.source,
            generation_kw=self.generation_kw,
            load_kw=self.load_kw,
            grid_import_kw=self.grid_import_kw,
            grid_export_kw=self.grid_export_kw,
            energy_kwh=self.energy_kwh,
            battery_soc=self.battery_soc,
        )


class TelemetryBatchCreate(BaseModel):
    """`POST /telemetry/readings/batch` request body."""

    readings: list[TelemetryReadingCreate] = Field(..., min_length=1)


class TelemetryReadingRead(BaseModel):
    """A stored reading, as returned by the query endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    meter_id: UUID
    energy_asset_id: UUID | None
    timestamp: datetime
    interval_start: datetime
    interval_end: datetime
    generation_kw: Decimal | None
    load_kw: Decimal | None
    grid_import_kw: Decimal | None
    grid_export_kw: Decimal | None
    energy_kwh: Decimal | None
    battery_soc: Decimal | None
    quality_status: TelemetryQualityStatus
    source: TelemetrySource
    created_at: datetime
    updated_at: datetime


class TelemetryIngestResult(BaseModel):
    """The outcome of submitting one reading.

    Flat rather than nested so the submitted values and the verdict read
    together. `id` is `null` when the submission was classified but
    deliberately not written — `duplicate` and `invalid_value`, per
    docs/04_DATA_MODEL.md — and `stored` says which happened. That satisfies
    the docs/05_API_SPEC.md principle that a mutating endpoint returns a stable
    resource ID and state.
    """

    id: UUID | None
    stored: bool
    quality_status: TelemetryQualityStatus
    reason: str | None = None

    meter_id: UUID
    energy_asset_id: UUID | None
    timestamp: datetime
    interval_start: datetime
    interval_end: datetime
    generation_kw: Decimal | None
    load_kw: Decimal | None
    grid_import_kw: Decimal | None
    grid_export_kw: Decimal | None
    energy_kwh: Decimal | None
    battery_soc: Decimal | None
    source: TelemetrySource


class TelemetryBatchResult(BaseModel):
    """Per-status summary of a batch, so partial success is reportable."""

    submitted: int
    ingested: int
    rejected: int
    counts_by_status: dict[TelemetryQualityStatus, int]
    readings: list[TelemetryIngestResult]


class TelemetryBucket(BaseModel):
    """One resampled bucket from a `resolution`-qualified interval query.

    `timestamp` is the bucket's start, so a bucket and a raw reading present the
    same time field to a client. Power channels are averaged and energy summed
    (docs/04_DATA_MODEL.md, entity 10).
    """

    timestamp: datetime
    generation_kw: Decimal | None
    load_kw: Decimal | None
    grid_import_kw: Decimal | None
    grid_export_kw: Decimal | None
    energy_kwh: Decimal | None
    reading_count: int


class TelemetrySeriesRead(BaseModel):
    """`GET /sites/{site_id}/telemetry` response.

    One series, in `readings`. Without a `resolution` the points are the stored
    readings; with one they are aggregated buckets. `resolution_seconds` says
    which, so a client never has to guess from the item shape.
    """

    site_id: UUID
    start: datetime
    end: datetime
    resolution_seconds: int | None
    count: int
    readings: list[TelemetryReadingRead] | list[TelemetryBucket] = Field(default_factory=list)
