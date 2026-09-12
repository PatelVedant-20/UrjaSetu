"""Pricing persistence — `price_components`.

Entity 18 of docs/04_DATA_MODEL.md, the `pricing` module of
docs/01_FINAL_ARCHITECTURE.md.

Persistence only: no formula, no coefficients, no thresholds. The engine never
sees this class — it works on the plain contract in
`app.domain.interfaces.pricing`, so the formula can be replaced without a
schema change.

One row is one explainable price for one trade. The columns are exactly the
fields the data model lists, with nothing added: the grid state and the
forecast this price rested on are already reachable through
`trades.grid_validation_id` and `orders.forecast_basis_id`, and duplicating
them here would create a second place for them to be wrong.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.market import Trade

# INR/kWh, matching `orders` and `trades` (docs/00_PROJECT_BIBLE.md section 6).
_PRICE = Numeric(12, 4)


class PriceComponents(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An explainable price calculation (docs/04_DATA_MODEL.md entity 18).

    History is kept rather than overwritten, exactly as `grid_validation_runs`
    keeps every validation: a trade may be repriced as the network or the
    forecast changes, and a settlement that has to be explained months later
    needs the calculation that actually applied, not only the last one. The
    authoritative breakdown for a trade is its most recent row.
    """

    __tablename__ = "price_components"

    trade_id: Mapped[UUID] = mapped_column(
        # CASCADE: a breakdown is a description of one trade and has no meaning
        # without it. This is the one place in the schema where that is true —
        # a grid validation run outlives its snapshot, but a price does not
        # outlive the thing it prices.
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False,
    )

    base_market_price: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    time_component: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    congestion_component: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    imbalance_component: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    local_renewable_component: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)
    final_price: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)

    # Which formula and coefficient set produced this, so a stored price stays
    # explainable after the formula moves on.
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False)

    trade: Mapped[Trade] = relationship()

    __table_args__ = (
        # The breakdown must add up. Without this the five columns could drift
        # from the total and the table would claim to explain a price it does
        # not explain — which is the only thing this table exists to do.
        CheckConstraint(
            "base_market_price + time_component + congestion_component "
            "+ imbalance_component + local_renewable_component = final_price",
            name="components_sum_to_final_price",
        ),
        CheckConstraint("base_market_price >= 0", name="base_price_not_negative"),
        CheckConstraint("final_price >= 0", name="final_price_not_negative"),
        # Congestion and imbalance are charges: scarcity and risk never pay the
        # buyer. The local-renewable term is the mirror image — an incentive
        # that can only ever reduce the price.
        CheckConstraint("congestion_component >= 0", name="congestion_is_a_charge"),
        CheckConstraint("imbalance_component >= 0", name="imbalance_is_a_charge"),
        CheckConstraint("local_renewable_component <= 0", name="local_renewable_is_an_incentive"),
        Index("ix_price_components_trade_id", "trade_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<PriceComponents id={self.id} trade={self.trade_id} "
            f"final={self.final_price} formula={self.formula_version!r}>"
        )
