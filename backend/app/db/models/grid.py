"""Grid persistence models — `grid_snapshots` and `grid_validation_runs`.

Entities 16 and 17 of docs/04_DATA_MODEL.md, the `grid` module of
docs/01_FINAL_ARCHITECTURE.md.

Persistence only: no power flow, no limits, no decision rules. The solver never
sees these classes — it works on the plain contract in
`app.domain.interfaces.grid`, so the engine can be replaced without a schema
change.

The topology itself is **not** re-modelled here: `grid_nodes` already exists
from Phase 1 (docs/04_DATA_MODEL.md entity 4) and is the one digital twin.
These two tables record *observations* and *judgements* about that twin.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.domain.enums import GridValidationDecision, GridValidationStatus

# kW (docs/00_PROJECT_BIBLE.md section 6).
_POWER = Numeric(14, 4)
# Per-unit voltage, four decimals — 1.0600 is a meaningful distance from 1.0599.
_PER_UNIT = Numeric(8, 4)
# Loading as a percentage of rating.
_PERCENT = Numeric(8, 3)


class GridSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Recorded network state, used for validation and audit
    (docs/04_DATA_MODEL.md entity 16).

    `feeder_id` is a plain grouping identifier, matching `grid_nodes.feeder_id`
    from Phase 1 — the data model marks its foreign keys explicitly and marks
    neither of these.

    Every measure is nullable: a snapshot may be taken from partial telemetry,
    and NULL means "not observed", never zero. Recording a missing measurement
    as 0 kW would make an unmonitored feeder look idle.
    """

    __tablename__ = "grid_snapshots"

    feeder_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    system_load_kw: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    generation_kw: Mapped[Decimal | None] = mapped_column(_POWER, nullable=True)
    transformer_loading_pct: Mapped[Decimal | None] = mapped_column(_PERCENT, nullable=True)
    max_line_loading_pct: Mapped[Decimal | None] = mapped_column(_PERCENT, nullable=True)
    min_voltage_pu: Mapped[Decimal | None] = mapped_column(_PER_UNIT, nullable=True)
    max_voltage_pu: Mapped[Decimal | None] = mapped_column(_PER_UNIT, nullable=True)

    validation_runs: Mapped[list[GridValidationRun]] = relationship(
        back_populates="snapshot", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "min_voltage_pu IS NULL OR min_voltage_pu >= 0", name="min_voltage_not_negative"
        ),
        CheckConstraint(
            "max_voltage_pu IS NULL OR max_voltage_pu >= 0", name="max_voltage_not_negative"
        ),
        CheckConstraint(
            "min_voltage_pu IS NULL OR max_voltage_pu IS NULL OR min_voltage_pu <= max_voltage_pu",
            name="voltage_range_ordered",
        ),
        CheckConstraint(
            "max_line_loading_pct IS NULL OR max_line_loading_pct >= 0",
            name="line_loading_not_negative",
        ),
        CheckConstraint(
            "transformer_loading_pct IS NULL OR transformer_loading_pct >= 0",
            name="transformer_loading_not_negative",
        ),
        Index("ix_grid_snapshots_feeder_id_captured_at", "feeder_id", "captured_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GridSnapshot id={self.id} feeder={self.feeder_id} at={self.captured_at}>"


class GridValidationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The result of simulating a proposed trade
    (docs/04_DATA_MODEL.md entity 17).

    `status` is what the validation found about the network; `decision` is what
    the platform concluded about the trade. They are stored separately because
    they answer different questions, and a later phase may reach a different
    decision from the same finding.

    `status` has three values, not two. A solver that crashed and a feeder that
    is genuinely overloaded are different facts, and recording both as "not
    safe" would lose the distinction that says whether the grid was ever
    actually checked.
    """

    __tablename__ = "grid_validation_runs"

    # Nullable, as the data model states: a scenario may be simulated before
    # any trade exists, so this is a back-reference rather than a requirement.
    #
    # Deliberately *not* a foreign key, even though `trades.grid_validation_id`
    # is one in the other direction. Constraining both would make the two
    # tables mutually dependent — neither row insertable before the other —
    # for a link that is already canonical from the trade's side. This column
    # stays the cheap lookup "which runs concerned this trade?", and
    # `trades.grid_validation_id` is the authoritative pointer.
    trade_id: Mapped[UUID | None] = mapped_column(nullable=True)
    grid_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grid_snapshots.id", ondelete="SET NULL"), nullable=True
    )

    simulation_engine: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Fingerprint of the request that produced this run, so an identical
    # scenario can be recognised and a stored result tied to its exact inputs
    # (docs/00_PROJECT_BIBLE.md: traceability).
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[GridValidationStatus] = mapped_column(
        pg_enum(GridValidationStatus, "grid_validation_status"), nullable=False
    )
    min_voltage_pu: Mapped[Decimal | None] = mapped_column(_PER_UNIT, nullable=True)
    max_voltage_pu: Mapped[Decimal | None] = mapped_column(_PER_UNIT, nullable=True)
    max_line_loading_pct: Mapped[Decimal | None] = mapped_column(_PERCENT, nullable=True)
    max_transformer_loading_pct: Mapped[Decimal | None] = mapped_column(_PERCENT, nullable=True)

    decision: Mapped[GridValidationDecision] = mapped_column(
        pg_enum(GridValidationDecision, "grid_validation_decision"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot: Mapped[GridSnapshot | None] = relationship(back_populates="validation_runs")

    __table_args__ = (
        # A safe network can only yield an accept, and an accept can only come
        # from a safe network. Without this the two columns could drift and a
        # rejected trade could look as though the grid had approved it. The
        # `unsafe` and `unknown` halves are both covered by the second clause:
        # a network nobody could assess is not a network that passed.
        CheckConstraint(
            "(status = 'safe' AND decision = 'accept') "
            "OR (status <> 'safe' AND decision <> 'accept')",
            name="decision_agrees_with_safety",
        ),
        CheckConstraint(
            "min_voltage_pu IS NULL OR max_voltage_pu IS NULL OR min_voltage_pu <= max_voltage_pu",
            name="voltage_range_ordered",
        ),
        Index("ix_grid_validation_runs_trade_id", "trade_id"),
        Index("ix_grid_validation_runs_grid_snapshot_id", "grid_snapshot_id"),
        Index("ix_grid_validation_runs_input_hash", "input_hash"),
        Index("ix_grid_validation_runs_decision", "decision"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<GridValidationRun id={self.id} status={self.status} "
            f"decision={self.decision} engine={self.simulation_engine!r}>"
        )
