"""Settlement persistence — `meter_reconciliations` and `settlements`.

Entities 19 and 20 of docs/04_DATA_MODEL.md, the `settlement` module of
docs/01_FINAL_ARCHITECTURE.md.

Persistence only: no tolerance, no fee, no accounting rules. The calculator
never sees these classes — it works on the plain contract in
`app.domain.interfaces.settlement`, so the rules can be replaced without a
schema change.

Two tables rather than one, because they answer different questions.
`meter_reconciliations` records what happened compared with what was agreed,
and exists even when the comparison could not be completed. `settlements`
records the money, and exists only once it can be.

Columns are exactly the fields the data model lists. The effective price is not
stored: it is recoverable as `gross_amount_inr / settled_kwh`, and reachable
through `price_components` for the trade, so a second copy would only create a
second place for it to be wrong.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.identity import User
from app.db.models.market import Trade
from app.db.types import pg_enum
from app.domain.enums import ReconciliationStatus, SettlementStatus

# kWh, matching `orders`, `trades` and `telemetry_readings`.
_ENERGY = Numeric(14, 4)
# INR. Wider than a price column because this is a total, not a unit rate, and
# two decimals because money is settled to the paise
# (docs/00_PROJECT_BIBLE.md section 6).
_AMOUNT = Numeric(16, 2)


class MeterReconciliation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Committed-versus-actual comparison (docs/04_DATA_MODEL.md entity 19).

    Written even when there was nothing to compare against. A window with no
    usable telemetry produces a row with `actual_kwh` NULL and status
    `awaiting_telemetry` — the record that the question was asked and could not
    yet be answered. Storing nothing instead would make an unmeasured trade
    indistinguishable from one never examined.
    """

    __tablename__ = "meter_reconciliations"

    trade_id: Mapped[UUID] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), nullable=False
    )

    committed_kwh: Mapped[Decimal] = mapped_column(_ENERGY, nullable=False)
    # NULL means "not measured", never zero. A meter that reported nothing and
    # a meter that reported zero are different facts, and only the second is a
    # shortfall anyone can be charged for.
    actual_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)
    # Signed: negative is a shortfall against the commitment. NULL while
    # nothing has been measured.
    deviation_kwh: Mapped[Decimal | None] = mapped_column(_ENERGY, nullable=True)

    within_tolerance: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # The part of the commitment the grid had to supply instead. Zero unless a
    # shortfall breached the tolerance.
    balancing_kwh: Mapped[Decimal] = mapped_column(_ENERGY, nullable=False)

    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        pg_enum(ReconciliationStatus, "reconciliation_status"), nullable=False
    )
    # Not in entity 19's field list, and not a measurement: this is the prose
    # the reconciliation policy wrote about its own decision, kept so a stored
    # comparison explains itself (docs/00_PROJECT_BIBLE.md: traceability).
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    trade: Mapped[Trade] = relationship()

    __table_args__ = (
        CheckConstraint("committed_kwh > 0", name="committed_positive"),
        CheckConstraint("actual_kwh IS NULL OR actual_kwh >= 0", name="actual_not_negative"),
        CheckConstraint("balancing_kwh >= 0", name="balancing_not_negative"),
        # An unmeasured window cannot have been found within tolerance, and a
        # measured one must carry its deviation. Without this the two columns
        # could drift and a trade nobody measured could read as compliant.
        CheckConstraint(
            "(actual_kwh IS NOT NULL AND deviation_kwh IS NOT NULL) "
            "OR (actual_kwh IS NULL AND deviation_kwh IS NULL AND NOT within_tolerance)",
            name="measurement_agrees_with_verdict",
        ),
        Index("ix_meter_reconciliations_trade_id", "trade_id"),
        Index("ix_meter_reconciliations_status", "reconciliation_status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<MeterReconciliation id={self.id} trade={self.trade_id} "
            f"committed={self.committed_kwh} actual={self.actual_kwh}>"
        )


class Settlement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Final financial allocation (docs/04_DATA_MODEL.md entity 20).

    Simulated. No payment gateway, no bank, no real money — these are ledger
    figures that Phase 8 can later audit and Phase 9 can display.

    Append-oriented. A correction does not overwrite: the previous row is
    marked `superseded` and a new one is written, so the history of what was
    settled and when stays readable. That is deliberately short of event
    sourcing, which the architecture does not call for.
    """

    __tablename__ = "settlements"

    trade_id: Mapped[UUID] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT on both parties: a settled amount names who owed it, and a user
    # cannot be removed while a financial record still points at them.
    buyer_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    seller_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    settled_kwh: Mapped[Decimal] = mapped_column(_ENERGY, nullable=False)

    gross_amount_inr: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    platform_fee_inr: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    balancing_charge_inr: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    # May be negative: a seller who delivered nothing owes the balancing charge
    # rather than earning anything, and forcing this to zero would break the
    # ledger identity below.
    seller_credit_inr: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    buyer_debit_inr: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)

    status: Mapped[SettlementStatus] = mapped_column(
        pg_enum(SettlementStatus, "settlement_status"), nullable=False
    )
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trade: Mapped[Trade] = relationship()
    buyer: Mapped[User] = relationship(foreign_keys=[buyer_user_id])
    seller: Mapped[User] = relationship(foreign_keys=[seller_user_id])

    __table_args__ = (
        # The ledger must balance: what the buyer is debited is what the seller
        # is credited plus everything the platform retained. A settlement whose
        # sides disagree is not a settlement, and this is the one invariant
        # that makes the row trustworthy without recomputing it.
        CheckConstraint(
            "buyer_debit_inr = seller_credit_inr + platform_fee_inr + balancing_charge_inr",
            name="ledger_balances",
        ),
        CheckConstraint("settled_kwh >= 0", name="settled_not_negative"),
        CheckConstraint("gross_amount_inr >= 0", name="gross_not_negative"),
        CheckConstraint("platform_fee_inr >= 0", name="platform_fee_not_negative"),
        CheckConstraint("balancing_charge_inr >= 0", name="balancing_charge_not_negative"),
        CheckConstraint("buyer_debit_inr >= 0", name="buyer_debit_not_negative"),
        Index("ix_settlements_trade_id", "trade_id"),
        Index("ix_settlements_buyer_user_id", "buyer_user_id"),
        Index("ix_settlements_seller_user_id", "seller_user_id"),
        Index("ix_settlements_status", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Settlement id={self.id} trade={self.trade_id} "
            f"kwh={self.settled_kwh} buyer_debit={self.buyer_debit_inr} "
            f"status={self.status}>"
        )
