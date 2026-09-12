"""Forecast persistence models — `forecast_runs` and `forecast_points`.

Entities 11 and 12 of docs/04_DATA_MODEL.md, the `forecasting` module of
docs/01_FINAL_ARCHITECTURE.md.

Persistence only: no algorithm, no provider knowledge beyond the identifiers
that say which provider produced a run. The schema is provider-agnostic by
design — swapping a baseline model for XGBoost or an OpenSTEF-backed provider
changes `provider`/`model_version` values, never the tables
(docs/06_OPEN_SOURCE_INTEGRATION.md section 5).
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
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.domain.enums import ForecastRunStatus, ForecastType

if TYPE_CHECKING:
    from app.db.models.assets import Site

# kW and kWh. Numeric rather than float: a forecast feeds surplus, which feeds
# order sizing in Phase 4 and settlement in Phase 8, where binary rounding is
# unacceptable.
_POWER = Numeric(14, 4)
_ENERGY = Numeric(14, 4)
# A probability in [0, 1].
_CONFIDENCE = Numeric(5, 4)


class ForecastRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One forecast execution (docs/04_DATA_MODEL.md entity 11).

    Deliberately not site-scoped: the data model puts `site_id` on the points,
    not the run, so one execution can cover several sites.

    A row is written *before* the provider is invoked, so a provider that
    raises or never returns still leaves a record saying a forecast was
    attempted, by whom, and that it failed.
    """

    __tablename__ = "forecast_runs"

    forecast_type: Mapped[ForecastType] = mapped_column(
        pg_enum(ForecastType, "forecast_type"), nullable=False
    )
    # Identity of the implementation that produced this run. Free-form strings
    # rather than an enum: adding a provider must never require a migration.
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    horizon_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[ForecastRunStatus] = mapped_column(
        pg_enum(ForecastRunStatus, "forecast_run_status"),
        nullable=False,
        server_default=ForecastRunStatus.PENDING.value,
    )
    # Why a run failed, kept so a failure is explainable without reading logs.
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    points: Mapped[list[ForecastPoint]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("horizon_end > horizon_start", name="horizon_end_after_start"),
        Index("ix_forecast_runs_forecast_type_horizon_start", "forecast_type", "horizon_start"),
        Index("ix_forecast_runs_status", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<ForecastRun id={self.id} type={self.forecast_type} "
            f"provider={self.provider!r} status={self.status}>"
        )


class ForecastPoint(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One predicted time bucket (docs/04_DATA_MODEL.md entity 12).

    `interval_start`/`interval_end` are when the predicted energy *flows*.
    When the prediction was *made* is `forecast_runs.created_at` — the two are
    never conflated.
    """

    __tablename__ = "forecast_points"

    forecast_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )

    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Nullable for the same reason as telemetry: NULL means the provider did
    # not predict this channel, which is distinct from predicting zero.
    predicted_kw: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    predicted_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)
    # Optional because not every provider is probabilistic. A naive baseline
    # has no meaningful uncertainty, and inventing one would be worse than
    # reporting none.
    confidence: Mapped[Decimal | None] = mapped_column(_CONFIDENCE, nullable=True)
    lower_bound: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    upper_bound: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)

    run: Mapped[ForecastRun] = relationship(back_populates="points")
    site: Mapped[Site] = relationship()

    __table_args__ = (
        # One prediction per site per bucket per run. Without this a retried
        # write could double a site's forecast and, through surplus, double the
        # energy it appears able to sell.
        UniqueConstraint(
            "forecast_run_id",
            "site_id",
            "interval_start",
            name="uq_forecast_points_forecast_run_id_site_id_interval_start",
        ),
        CheckConstraint("interval_end > interval_start", name="interval_end_after_start"),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_is_a_probability"
        ),
        # Only checked when both are present; a provider may give one bound.
        CheckConstraint(
            "lower_bound IS NULL OR upper_bound IS NULL OR lower_bound <= upper_bound",
            name="bounds_ordered",
        ),
        # The surplus query: "this site's predictions across a window".
        Index("ix_forecast_points_site_id_interval_start", "site_id", "interval_start"),
        Index("ix_forecast_points_forecast_run_id", "forecast_run_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<ForecastPoint id={self.id} site={self.site_id} "
            f"interval_start={self.interval_start} kw={self.predicted_kw}>"
        )
