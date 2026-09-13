"""Market persistence models — `market_sessions`, `orders`, `trades`.

Entities 13, 14 and 15 of docs/04_DATA_MODEL.md, the `market` module of
docs/01_FINAL_ARCHITECTURE.md.

Persistence only: no matching, no pricing formula, no eligibility rules. The
matching engine never sees these classes — it works on the plain contract in
`app.domain.interfaces.market`, so the algorithm can be replaced without a
schema change.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
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
from app.domain.enums import (
    MarketSessionStatus,
    MarketType,
    OrderSide,
    OrderStatus,
    TradeStatus,
)

if TYPE_CHECKING:
    from app.db.models.assets import GridNode, Site
    from app.db.models.forecasting import ForecastRun
    from app.db.models.identity import User

# kWh. Numeric rather than float: these quantities flow into settlement in
# Phase 8, where binary rounding is unacceptable.
_ENERGY = Numeric(14, 4)
# INR/kWh, to paise-level precision (docs/00_PROJECT_BIBLE.md section 6).
_PRICE = Numeric(12, 4)
# A dimensionless score in [0, 1].
_SCORE = Numeric(5, 4)


class MarketSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One market clearing window (docs/04_DATA_MODEL.md entity 13).

    Day-ahead: a session covers one `market_date`, takes orders while open,
    stops taking them when closed, and is cleared once.
    """

    __tablename__ = "market_sessions"

    market_date: Mapped[date] = mapped_column(Date(), nullable=False)
    market_type: Mapped[MarketType] = mapped_column(
        pg_enum(MarketType, "market_type"),
        nullable=False,
        server_default=MarketType.DAY_AHEAD.value,
    )
    status: Mapped[MarketSessionStatus] = mapped_column(
        pg_enum(MarketSessionStatus, "market_session_status"),
        nullable=False,
        server_default=MarketSessionStatus.OPEN.value,
    )

    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    orders: Mapped[list[Order]] = relationship(
        back_populates="market_session", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # One session per market date per type. Two open sessions for the same
        # day would split the book, and the same energy could be sold in both.
        UniqueConstraint(
            "market_date", "market_type", name="uq_market_sessions_market_date_market_type"
        ),
        CheckConstraint(
            "closed_at IS NULL OR opened_at IS NULL OR closed_at >= opened_at",
            name="closed_after_opened",
        ),
        CheckConstraint(
            "cleared_at IS NULL OR closed_at IS NULL OR cleared_at >= closed_at",
            name="cleared_after_closed",
        ),
        Index("ix_market_sessions_status", "status"),
        Index("ix_market_sessions_market_date", "market_date"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<MarketSession id={self.id} date={self.market_date} status={self.status}>"


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A buy or sell intent (docs/04_DATA_MODEL.md entity 14).

    Price bounds are side-specific and enforced by the database: a BUY must
    carry the most it will pay, a SELL the least it will accept. Without that,
    an unpriced order could trade at whatever the counterparty asked.
    """

    __tablename__ = "orders"

    market_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT, not CASCADE: an order is a commitment, and deleting a user must
    # not silently erase what they offered to the market.
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False
    )
    # Nullable, mirroring `sites.grid_node_id`: a site may be registered before
    # it is mapped onto the digital twin, and Phase 6 is what makes the node
    # matter.
    node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grid_nodes.id", ondelete="RESTRICT"), nullable=True
    )

    side: Mapped[OrderSide] = mapped_column(pg_enum(OrderSide, "order_side"), nullable=False)
    energy_kwh: Mapped[Decimal] = mapped_column(_ENERGY, nullable=False)

    min_price_inr_per_kwh: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)
    max_price_inr_per_kwh: Mapped[Decimal | None] = mapped_column(_PRICE, nullable=True)

    delivery_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # The forecast that justified this order, so a sell can be traced back to
    # the surplus it was based on (docs/00_PROJECT_BIBLE.md: traceability).
    # Nullable: a buy order needs no forecast basis.
    forecast_basis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("forecast_runs.id", ondelete="SET NULL"), nullable=True
    )
    # Frozen at placement so a later change to a participant's standing cannot
    # retroactively alter how a past clearing behaved.
    reliability_score_snapshot: Mapped[Decimal | None] = mapped_column(_SCORE, nullable=True)

    status: Mapped[OrderStatus] = mapped_column(
        pg_enum(OrderStatus, "order_status"),
        nullable=False,
        server_default=OrderStatus.OPEN.value,
    )
    # Energy already committed to proposed trades. Kept on the row so the book
    # can be rebuilt without summing trades on every read, and so a partially
    # matched order re-enters the book at its remainder.
    matched_kwh: Mapped[Decimal] = mapped_column(_ENERGY, nullable=False, server_default="0")

    market_session: Mapped[MarketSession] = relationship(back_populates="orders")
    user: Mapped[User] = relationship()
    site: Mapped[Site] = relationship()
    node: Mapped[GridNode | None] = relationship()
    forecast_basis: Mapped[ForecastRun | None] = relationship()

    @property
    def remaining_kwh(self) -> Decimal:
        """Energy still available to match."""
        return self.energy_kwh - self.matched_kwh

    __table_args__ = (
        CheckConstraint("energy_kwh > 0", name="energy_positive"),
        CheckConstraint("delivery_end > delivery_start", name="delivery_end_after_start"),
        CheckConstraint(
            "matched_kwh >= 0 AND matched_kwh <= energy_kwh", name="matched_within_energy"
        ),
        # docs/04_DATA_MODEL.md entity 14: "buy requires max price",
        # "sell requires min price".
        CheckConstraint(
            "(side <> 'buy') OR (max_price_inr_per_kwh IS NOT NULL)",
            name="buy_requires_max_price",
        ),
        CheckConstraint(
            "(side <> 'sell') OR (min_price_inr_per_kwh IS NOT NULL)",
            name="sell_requires_min_price",
        ),
        CheckConstraint(
            "min_price_inr_per_kwh IS NULL OR min_price_inr_per_kwh >= 0",
            name="min_price_not_negative",
        ),
        CheckConstraint(
            "max_price_inr_per_kwh IS NULL OR max_price_inr_per_kwh >= 0",
            name="max_price_not_negative",
        ),
        CheckConstraint(
            "reliability_score_snapshot IS NULL " "OR reliability_score_snapshot BETWEEN 0 AND 1",
            name="reliability_score_is_a_ratio",
        ),
        # The order-book query: "active orders on this side of this session".
        Index("ix_orders_market_session_id_side_status", "market_session_id", "side", "status"),
        Index("ix_orders_user_id", "user_id"),
        Index("ix_orders_site_id", "site_id"),
        Index("ix_orders_node_id", "node_id"),
        Index("ix_orders_forecast_basis_id", "forecast_basis_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Order id={self.id} side={self.side} kwh={self.energy_kwh} " f"status={self.status}>"
        )


class Trade(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A matched market transaction (docs/04_DATA_MODEL.md entity 15).

    Created by clearing as a **candidate**. docs/05_API_SPEC.md is explicit
    that clearing "does not silently bypass grid validation", so a trade starts
    `proposed` and only later phases approve or commit it.

    `grid_validation_id` points at the Phase 5 validation that judged this
    trade. It stays NULL until a validation has run; a matched trade that has
    never been near the grid must be distinguishable from one that passed.
    """

    __tablename__ = "trades"
    fill_sequence: Mapped[int] = mapped_column(default=1, server_default="1")

    buy_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    sell_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )

    quantity_kwh: Mapped[Decimal] = mapped_column(_ENERGY, nullable=False)
    clearing_price_inr_per_kwh: Mapped[Decimal] = mapped_column(_PRICE, nullable=False)

    delivery_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivery_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # RESTRICT, not CASCADE or SET NULL: the validation is the evidence for
    # whatever the platform decided about this trade, so it must not be
    # possible to delete the evidence while the trade still cites it.
    grid_validation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grid_validation_runs.id", ondelete="RESTRICT"), nullable=True
    )

    # `proposed` is the only value the vocabulary currently holds; approval and
    # commitment states arrive with the phases that define them.
    status: Mapped[TradeStatus] = mapped_column(
        pg_enum(TradeStatus, "trade_status"),
        nullable=False,
        server_default=TradeStatus.PROPOSED.value,
    )
    # Declared because docs/04_DATA_MODEL.md entity 15 lists it. Stays NULL
    # until a settlement phase introduces a committed state to set it with.
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Which clearing produced this candidate, so a trade can be attributed to a
    # specific engine at a specific version.
    matching_engine: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matching_engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    buy_order: Mapped[Order] = relationship(foreign_keys=[buy_order_id])
    sell_order: Mapped[Order] = relationship(foreign_keys=[sell_order_id])

    __table_args__ = (
        CheckConstraint("quantity_kwh > 0", name="quantity_positive"),
        CheckConstraint("clearing_price_inr_per_kwh >= 0", name="clearing_price_not_negative"),
        CheckConstraint("delivery_end > delivery_start", name="delivery_end_after_start"),
        CheckConstraint("buy_order_id <> sell_order_id", name="distinct_orders"),
        # Distinct partial fills may share a pairing; the same numbered fill
        # cannot be inserted twice. Legacy clearing uses the default first fill.
        UniqueConstraint(
            "buy_order_id",
            "sell_order_id",
            "delivery_start",
            "fill_sequence",
            name="uq_trades_buy_order_id_sell_order_id_delivery_start",
        ),
        Index("ix_trades_buy_order_id", "buy_order_id"),
        Index("ix_trades_sell_order_id", "sell_order_id"),
        Index("ix_trades_status", "status"),
        Index("ix_trades_grid_validation_id", "grid_validation_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Trade id={self.id} kwh={self.quantity_kwh} "
            f"price={self.clearing_price_inr_per_kwh} status={self.status}>"
        )
