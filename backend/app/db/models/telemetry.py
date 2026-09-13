"""Telemetry persistence model — `telemetry_readings`.

Entity 10 of docs/04_DATA_MODEL.md, the `telemetry` module of
docs/01_FINAL_ARCHITECTURE.md.

Persistence only: no ingestion rules, no quality classification, no knowledge
of any adapter, vendor or file format. Quality is decided by
`app.domain.policies.telemetry_quality` and merely stored here.

Units follow docs/00_PROJECT_BIBLE.md section 6 exactly — kW, kWh, percent,
timezone-aware UTC — and are never converted at this layer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.domain.enums import TelemetryQualityStatus, TelemetrySource

if TYPE_CHECKING:
    from app.db.models.assets import EnergyAsset, Meter

# kW and kWh. Numeric rather than float: these values flow into reconciliation
# and settlement arithmetic in Phase 8, where binary rounding is unacceptable.
_POWER = Numeric(14, 4)
_ENERGY = Numeric(14, 4)
# Percent, two decimals.
_PERCENT = Numeric(5, 2)


class TelemetryReading(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One normalized measurement from a meter, optionally scoped to an asset.

    docs/04_DATA_MODEL.md allows `BIGINT/UUID` for the primary key; UUID is used
    because section 6 of the Project Bible locks IDs to UUIDs project-wide and
    every other table already follows the shared `UUIDPrimaryKeyMixin`.

    `created_at`/`updated_at` from `TimestampMixin` are the ingestion metadata:
    when the platform received the row, as opposed to `timestamp`/`interval_*`
    which describe when the energy actually flowed. Keeping both is what makes
    late-arriving data analysable.
    """

    __tablename__ = "telemetry_readings"

    meter_id: Mapped[UUID] = mapped_column(
        ForeignKey("meters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable per the data model: a whole-site meter reading is not attributable
    # to one asset, while a PV or battery channel is.
    energy_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("energy_assets.id", ondelete="CASCADE"),
        nullable=True,
    )

    # The reading's canonical instant, as reported by the source.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Explicit interval bounds are mandated by docs/00_PROJECT_BIBLE.md section 6.
    # The half-open interval [interval_start, interval_end) is what `energy_kwh`
    # is measured over.
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Every measurement is nullable, and NULL means "this device does not
    # measure this channel" — deliberately distinct from 0, which means
    # "measured, and it was zero". A meter with no PV reports no generation; it
    # does not report zero generation.
    generation_kw: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    load_kw: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    grid_import_kw: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    grid_export_kw: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    energy_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)
    generation_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)
    load_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)
    grid_import_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)
    grid_export_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)
    battery_soc: Mapped[Decimal | None] = mapped_column(_PERCENT, nullable=True)

    quality_status: Mapped[TelemetryQualityStatus] = mapped_column(
        pg_enum(TelemetryQualityStatus, "telemetry_quality_status"),
        nullable=False,
        server_default=TelemetryQualityStatus.VALID.value,
    )
    source: Mapped[TelemetrySource] = mapped_column(
        pg_enum(TelemetrySource, "telemetry_source"), nullable=False
    )

    meter: Mapped[Meter] = relationship()
    energy_asset: Mapped[EnergyAsset | None] = relationship()

    __table_args__ = (
        # The natural key of interval metering. NULLS NOT DISTINCT (PostgreSQL
        # 15+) is essential: without it PostgreSQL treats every NULL
        # `energy_asset_id` as unique, so whole-site readings could be inserted
        # twice for the same interval and silently double-count energy at
        # settlement. The service turns a violation of this into a `duplicate`
        # quality outcome rather than a crash.
        UniqueConstraint(
            "meter_id",
            "energy_asset_id",
            "interval_start",
            name="uq_telemetry_readings_meter_id_energy_asset_id_interval_start",
            postgresql_nulls_not_distinct=True,
        ),
        # Equality on interval_start is allowed so an instantaneous sample can
        # be stored as a zero-length interval.
        CheckConstraint("interval_end >= interval_start", name="interval_end_not_before_start"),
        CheckConstraint(
            "generation_kw IS NULL OR generation_kw >= 0", name="generation_kw_not_negative"
        ),
        CheckConstraint("load_kw IS NULL OR load_kw >= 0", name="load_kw_not_negative"),
        CheckConstraint(
            "grid_import_kw IS NULL OR grid_import_kw >= 0", name="grid_import_kw_not_negative"
        ),
        CheckConstraint(
            "grid_export_kw IS NULL OR grid_export_kw >= 0", name="grid_export_kw_not_negative"
        ),
        CheckConstraint("energy_kwh IS NULL OR energy_kwh >= 0", name="energy_kwh_not_negative"),
        CheckConstraint(
            "battery_soc IS NULL OR battery_soc BETWEEN 0 AND 100", name="battery_soc_percent"
        ),
        # docs/04_DATA_MODEL.md: "(site/meter, timestamp)". Site-scoped queries
        # reach this through `meters.site_id`, which Phase 1 already indexes;
        # the data model itself specifies reaching site and grid_node "via join",
        # so no site_id is denormalised onto this table.
        Index("ix_telemetry_readings_meter_id_interval_start", "meter_id", "interval_start"),
        Index("ix_telemetry_readings_meter_id_timestamp", "meter_id", "timestamp"),
        Index("ix_telemetry_readings_energy_asset_id", "energy_asset_id"),
        # Serves "latest *valid* reading" (docs/05_API_SPEC.md) without scanning
        # readings that were rejected.
        Index(
            "ix_telemetry_readings_meter_id_quality_status_interval_start",
            "meter_id",
            "quality_status",
            "interval_start",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<TelemetryReading id={self.id} meter={self.meter_id} "
            f"interval_start={self.interval_start} quality={self.quality_status}>"
        )
