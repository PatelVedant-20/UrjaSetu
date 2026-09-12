"""Telemetry persistence queries.

Query construction only — no ingestion rules and no quality classification
(docs/03_REPOSITORY_STRUCTURE.md). Like every repository here, it never
commits: the caller owns the transaction boundary.

Site-scoped queries join through `meters.site_id` rather than reading a
denormalised column, because docs/04_DATA_MODEL.md specifies reaching site and
grid node "via join" and lists no `site_id` on this table.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import Select, and_, func, select

from app.db.models.assets import Meter
from app.db.models.telemetry import TelemetryReading
from app.domain.enums import TelemetryQualityStatus
from app.repositories.base import BaseRepository


class AggregatedReading(NamedTuple):
    """One resampled bucket from `GET /sites/{site_id}/telemetry?resolution=...`.

    Power channels are averaged over the bucket and energy is summed, which is
    the only combination that keeps kW and kWh meaning what
    docs/00_PROJECT_BIBLE.md section 6 says they mean.
    """

    bucket_start: datetime
    generation_kw: Decimal | None
    load_kw: Decimal | None
    grid_import_kw: Decimal | None
    grid_export_kw: Decimal | None
    energy_kwh: Decimal | None
    reading_count: int


class TelemetryRepository(BaseRepository[TelemetryReading]):
    model = TelemetryReading

    # -- writes ----------------------------------------------------------

    def add_all(self, readings: Sequence[TelemetryReading]) -> Sequence[TelemetryReading]:
        """Stage many readings and flush once.

        One flush rather than one per row: batch ingestion is the common path
        and a per-row round trip dominates its cost.
        """
        self.session.add_all(readings)
        self.session.flush()
        return readings

    # -- series context (used by the quality classifier) ------------------

    def latest_interval_start(
        self, meter_id: UUID, energy_asset_id: UUID | None
    ) -> datetime | None:
        """Newest `interval_start` already stored for this exact series.

        `IS NULL` is used explicitly for a null asset id, because `= NULL` never
        matches and would silently report an empty series.
        """
        stmt = select(func.max(TelemetryReading.interval_start)).where(
            TelemetryReading.meter_id == meter_id,
            self._asset_predicate(energy_asset_id),
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def exists_for_interval(
        self, meter_id: UUID, energy_asset_id: UUID | None, interval_start: datetime
    ) -> bool:
        """Whether this series already has a reading covering that interval."""
        stmt = select(TelemetryReading.id).where(
            TelemetryReading.meter_id == meter_id,
            self._asset_predicate(energy_asset_id),
            TelemetryReading.interval_start == interval_start,
        )
        return self.session.execute(stmt).first() is not None

    # -- reads -----------------------------------------------------------

    def latest_for_site(self, site_id: UUID, *, only_valid: bool = True) -> TelemetryReading | None:
        """Most recent reading for a site.

        `only_valid` defaults to True because docs/05_API_SPEC.md defines
        `/telemetry/latest` as the latest *valid* reading, and the stale
        fallback in docs/01_FINAL_ARCHITECTURE.md needs last-known-*valid*.
        """
        stmt = self._site_scoped().order_by(TelemetryReading.interval_start.desc()).limit(1)
        if only_valid:
            stmt = stmt.where(TelemetryReading.quality_status == TelemetryQualityStatus.VALID)
        return self.session.execute(stmt.where(Meter.site_id == site_id)).scalars().first()

    def list_for_site(
        self,
        site_id: UUID,
        *,
        start: datetime,
        end: datetime,
        only_valid: bool = False,
        limit: int = 1000,
        offset: int = 0,
    ) -> Sequence[TelemetryReading]:
        """Readings whose `timestamp` falls within [start, end], inclusive.

        The public historical window is expressed on `timestamp` — the instant a
        reading reports — because that is the axis a caller of
        `GET /sites/{site_id}/telemetry` is asking about, and it is inclusive at
        both ends so a window named by two readings returns both of them.

        Problematic readings are included by default and keep their
        `quality_status`: historical data stays queryable, and a time-series
        view has to show its gaps.
        """
        stmt = (
            self._site_scoped()
            .where(
                Meter.site_id == site_id,
                TelemetryReading.timestamp >= start,
                TelemetryReading.timestamp <= end,
            )
            .order_by(TelemetryReading.timestamp.asc())
            .limit(limit)
            .offset(offset)
        )
        if only_valid:
            stmt = stmt.where(TelemetryReading.quality_status == TelemetryQualityStatus.VALID)
        return self.session.execute(stmt).scalars().all()

    def aggregate_for_site(
        self,
        site_id: UUID,
        *,
        start: datetime,
        end: datetime,
        resolution: timedelta,
        only_valid: bool = True,
    ) -> Sequence[AggregatedReading]:
        """Resample a site's readings into fixed buckets.

        `date_bin` anchors buckets to `start`, so the same window and resolution
        always produce the same boundaries regardless of when the query runs.

        The window matches `list_for_site` — closed, on `timestamp` — but the
        quality filter deliberately does not: only usable readings are
        aggregated, because averaging a stale or invalid reading into a summary
        would launder it into apparent truth. Historical readings stay
        queryable through `list_for_site` and through `count_by_quality`.
        """
        bucket = func.date_bin(resolution, TelemetryReading.timestamp, start).label("bucket")
        stmt = (
            select(
                bucket,
                func.avg(TelemetryReading.generation_kw),
                func.avg(TelemetryReading.load_kw),
                func.avg(TelemetryReading.grid_import_kw),
                func.avg(TelemetryReading.grid_export_kw),
                func.sum(TelemetryReading.energy_kwh),
                func.count(TelemetryReading.id),
            )
            .join(Meter, Meter.id == TelemetryReading.meter_id)
            .where(
                Meter.site_id == site_id,
                TelemetryReading.timestamp >= start,
                TelemetryReading.timestamp <= end,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        if only_valid:
            stmt = stmt.where(TelemetryReading.quality_status == TelemetryQualityStatus.VALID)

        return [AggregatedReading(*row) for row in self.session.execute(stmt).all()]

    def count_by_quality(self, site_id: UUID) -> dict[TelemetryQualityStatus, int]:
        """How many readings a site holds in each quality state."""
        stmt = (
            select(TelemetryReading.quality_status, func.count(TelemetryReading.id))
            .join(Meter, Meter.id == TelemetryReading.meter_id)
            .where(Meter.site_id == site_id)
            .group_by(TelemetryReading.quality_status)
        )
        return dict(self.session.execute(stmt).all())  # type: ignore[arg-type]

    def list_for_meter(
        self, meter_id: UUID, *, start: datetime, end: datetime
    ) -> Sequence[TelemetryReading]:
        stmt = (
            select(TelemetryReading)
            .where(
                TelemetryReading.meter_id == meter_id,
                TelemetryReading.interval_start >= start,
                TelemetryReading.interval_start < end,
            )
            .order_by(TelemetryReading.interval_start.asc())
        )
        return self.session.execute(stmt).scalars().all()

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _asset_predicate(energy_asset_id: UUID | None):  # type: ignore[no-untyped-def]
        if energy_asset_id is None:
            return TelemetryReading.energy_asset_id.is_(None)
        return TelemetryReading.energy_asset_id == energy_asset_id

    @staticmethod
    def _site_scoped() -> Select[tuple[TelemetryReading]]:
        return select(TelemetryReading).join(Meter, and_(Meter.id == TelemetryReading.meter_id))
