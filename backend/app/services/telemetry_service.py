"""Telemetry service — ingestion, quality classification and retrieval.

The single entry point between any telemetry source and the database:

    adapter -> NormalizedReading -> telemetry_service -> repository -> PostgreSQL

It owns the transaction boundary for ingestion (docs/04_DATA_MODEL.md,
"Transaction Boundaries") and knows nothing about HTTP. It decides no quality
rules either: it gathers the series context a reading arrived in and hands it
to `app.domain.policies.telemetry_quality`, which is the one place a status is
decided.

A reading is never silently dropped. Duplicates, stale data, out-of-order
arrivals and unavailable sources are all *recorded* with the status that says
so, because docs/00_PROJECT_BIBLE.md requires that a stale or missing source
never breaks the platform and that every decision stay explainable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models.telemetry import TelemetryReading
from app.domain.enums import TelemetryQualityStatus
from app.domain.interfaces.telemetry import NormalizedReading
from app.domain.policies.telemetry_quality import (
    DEFAULT_STALENESS_THRESHOLD,
    QualityAssessment,
    SeriesContext,
    classify_reading,
)
from app.repositories import (
    AggregatedReading,
    EnergyAssetRepository,
    MeterRepository,
    SiteRepository,
    TelemetryRepository,
)

# Statuses whose readings are classified and reported but never written.
#
# Both would violate a database invariant if stored: a DUPLICATE collides with
# the table's natural key, and an INVALID_VALUE by definition fails one of the
# CHECK constraints that make stored telemetry trustworthy. Attempting the
# insert would raise and take the whole ingestion down, which
# docs/00_PROJECT_BIBLE.md forbids — a bad source must never break the
# platform. The caller still learns the submission arrived and why it was
# rejected.
NON_STORABLE_STATUSES = frozenset(
    {TelemetryQualityStatus.DUPLICATE, TelemetryQualityStatus.INVALID_VALUE}
)


@dataclass(frozen=True, slots=True)
class IngestionOutcome:
    """What happened to one submitted reading.

    `reading` is `None` when the submission was classified but deliberately not
    written — see `NON_STORABLE_STATUSES`. The caller still learns the
    submission was seen and why it was rejected.
    """

    assessment: QualityAssessment
    reading: TelemetryReading | None

    @property
    def stored(self) -> bool:
        return self.reading is not None

    @property
    def quality_status(self) -> TelemetryQualityStatus:
        return self.assessment.status


@dataclass(slots=True)
class BatchIngestionResult:
    """Per-status summary of a batch, so a caller can report partial success."""

    outcomes: list[IngestionOutcome] = field(default_factory=list)

    @property
    def accepted(self) -> int:
        """Readings stored with a usable status."""
        return sum(1 for o in self.outcomes if o.assessment.is_usable and o.stored)

    @property
    def flagged(self) -> int:
        """Submissions that were not usable, whether or not they were stored."""
        return len(self.outcomes) - self.accepted

    @property
    def stored(self) -> int:
        """Submissions that resulted in a row."""
        return sum(1 for o in self.outcomes if o.stored)

    @property
    def rejected(self) -> int:
        """Submissions classified but deliberately not written."""
        return sum(1 for o in self.outcomes if not o.stored)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    def counts_by_status(self) -> dict[TelemetryQualityStatus, int]:
        counts: dict[TelemetryQualityStatus, int] = {}
        for outcome in self.outcomes:
            counts[outcome.quality_status] = counts.get(outcome.quality_status, 0) + 1
        return counts


def ingest_reading(
    session: Session,
    reading: NormalizedReading,
    *,
    at: datetime | None = None,
    staleness_threshold: timedelta = DEFAULT_STALENESS_THRESHOLD,
) -> IngestionOutcome:
    """Classify and store one normalized reading. One transaction."""
    _require_meter(session, reading.meter_id)
    _require_asset(session, reading.energy_asset_id)

    evaluated_at = at or datetime.now(UTC)
    outcome = _classify_and_build(
        session, reading, evaluated_at=evaluated_at, staleness_threshold=staleness_threshold
    )

    if outcome.reading is not None:
        TelemetryRepository(session).add(outcome.reading)
        session.commit()
        session.refresh(outcome.reading)
    return outcome


def ingest_batch(
    session: Session,
    readings: Sequence[NormalizedReading],
    *,
    at: datetime | None = None,
    staleness_threshold: timedelta = DEFAULT_STALENESS_THRESHOLD,
) -> BatchIngestionResult:
    """Classify and store many readings in a single transaction.

    All-or-nothing on purpose: a batch is one meter upload, and a half-written
    upload would leave a series with gaps that look like real missing data.

    Readings are classified in submission order, and each one's context
    includes the readings already staged earlier in the same batch — so a batch
    containing the same interval twice records the second as `duplicate`
    exactly as it would across two separate calls.
    """
    evaluated_at = at or datetime.now(UTC)
    result = BatchIngestionResult()

    # Series state accumulated within this batch, keyed by (meter, asset).
    staged_latest: dict[tuple[UUID, UUID | None], datetime] = {}
    staged_intervals: set[tuple[UUID, UUID | None, datetime]] = set()

    verified_meters: set[UUID] = set()
    verified_assets: set[UUID] = set()

    for reading in readings:
        if reading.meter_id not in verified_meters:
            _require_meter(session, reading.meter_id)
            verified_meters.add(reading.meter_id)
        if reading.energy_asset_id is not None and reading.energy_asset_id not in verified_assets:
            _require_asset(session, reading.energy_asset_id)
            verified_assets.add(reading.energy_asset_id)

        series = (reading.meter_id, reading.energy_asset_id)
        outcome = _classify_and_build(
            session,
            reading,
            evaluated_at=evaluated_at,
            staleness_threshold=staleness_threshold,
            extra_latest=staged_latest.get(series),
            extra_duplicate=(series + (reading.interval_start,)) in staged_intervals,
        )
        result.outcomes.append(outcome)

        if not outcome.stored:
            continue
        staged_intervals.add(series + (reading.interval_start,))
        previous = staged_latest.get(series)
        if previous is None or reading.interval_start > previous:
            staged_latest[series] = reading.interval_start

    storable = [o.reading for o in result.outcomes if o.reading is not None]
    if storable:
        TelemetryRepository(session).add_all(storable)
    session.commit()
    return result


def get_latest_for_site(
    session: Session, site_id: UUID, *, only_valid: bool = True
) -> TelemetryReading | None:
    """Latest reading for a site, valid-only by default.

    Returns `None` rather than raising when a site has no telemetry yet — an
    empty series is a normal state, not an error.
    """
    _require_site(session, site_id)
    return TelemetryRepository(session).latest_for_site(site_id, only_valid=only_valid)


def get_interval_for_site(
    session: Session,
    site_id: UUID,
    *,
    start: datetime,
    end: datetime,
    resolution: timedelta | None = None,
    only_valid: bool = False,
    limit: int = 1000,
    offset: int = 0,
) -> Sequence[TelemetryReading] | Sequence[AggregatedReading]:
    """Readings in [start, end), raw or resampled.

    With `resolution` set the result is a sequence of `AggregatedReading`
    buckets; without it, the stored readings themselves.
    """
    _require_site(session, site_id)
    repo = TelemetryRepository(session)

    if resolution is not None:
        return repo.aggregate_for_site(
            site_id, start=start, end=end, resolution=resolution, only_valid=True
        )
    return repo.list_for_site(
        site_id, start=start, end=end, only_valid=only_valid, limit=limit, offset=offset
    )


def get_quality_summary(session: Session, site_id: UUID) -> dict[TelemetryQualityStatus, int]:
    """How many readings a site holds in each quality state."""
    _require_site(session, site_id)
    return TelemetryRepository(session).count_by_quality(site_id)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _classify_and_build(
    session: Session,
    reading: NormalizedReading,
    *,
    evaluated_at: datetime,
    staleness_threshold: timedelta,
    extra_latest: datetime | None = None,
    extra_duplicate: bool = False,
) -> IngestionOutcome:
    """Classify a reading against its series, then build the row to store.

    `extra_latest`/`extra_duplicate` carry state staged earlier in the same
    batch that is not in the database yet.
    """
    repo = TelemetryRepository(session)

    stored_latest = repo.latest_interval_start(reading.meter_id, reading.energy_asset_id)
    latest = max(filter(None, (stored_latest, extra_latest)), default=None)
    duplicate = extra_duplicate or repo.exists_for_interval(
        reading.meter_id, reading.energy_asset_id, reading.interval_start
    )

    assessment = classify_reading(
        reading,
        evaluated_at=evaluated_at,
        context=SeriesContext(latest_interval_start=latest, duplicate_exists=duplicate),
        staleness_threshold=staleness_threshold,
    )

    storable = (
        None if assessment.status in NON_STORABLE_STATUSES else _to_model(reading, assessment)
    )
    return IngestionOutcome(assessment=assessment, reading=storable)


def _to_model(reading: NormalizedReading, assessment: QualityAssessment) -> TelemetryReading:
    """Map the normalized contract onto the persistence model.

    A straight field-for-field copy. No unit conversion happens here, or
    anywhere else in the domain (docs/00_PROJECT_BIBLE.md section 6).
    """
    return TelemetryReading(
        meter_id=reading.meter_id,
        energy_asset_id=reading.energy_asset_id,
        timestamp=reading.timestamp,
        interval_start=reading.interval_start,
        interval_end=reading.interval_end,
        generation_kw=reading.generation_kw,
        load_kw=reading.load_kw,
        grid_import_kw=reading.grid_import_kw,
        grid_export_kw=reading.grid_export_kw,
        energy_kwh=reading.energy_kwh,
        battery_soc=reading.battery_soc,
        quality_status=assessment.status,
        source=reading.source,
    )


def _require_meter(session: Session, meter_id: UUID) -> None:
    if MeterRepository(session).get(meter_id) is None:
        raise NotFoundError(
            "Meter not found.", code="METER_NOT_FOUND", details={"id": str(meter_id)}
        )


def _require_asset(session: Session, energy_asset_id: UUID | None) -> None:
    if energy_asset_id is None:
        return
    if EnergyAssetRepository(session).get(energy_asset_id) is None:
        raise NotFoundError(
            "Energy asset not found.",
            code="ENERGY_ASSET_NOT_FOUND",
            details={"id": str(energy_asset_id)},
        )


def _require_site(session: Session, site_id: UUID) -> None:
    if SiteRepository(session).get(site_id) is None:
        raise NotFoundError("Site not found.", code="SITE_NOT_FOUND", details={"id": str(site_id)})
