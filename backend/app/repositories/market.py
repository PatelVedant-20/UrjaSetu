"""Market persistence queries.

Query construction only — no matching, no pricing, no eligibility
(docs/03_REPOSITORY_STRUCTURE.md). Never commits: the caller owns the
transaction boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.db.models.market import MarketSession, Order, Trade
from app.domain.enums import MarketSessionStatus, MarketType, OrderSide, OrderStatus
from app.repositories.base import BaseRepository

# Statuses whose orders still hold matchable energy.
ACTIVE_ORDER_STATUSES = (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)


class MarketSessionRepository(BaseRepository[MarketSession]):
    model = MarketSession

    def get_for_date(
        self, market_date: date, market_type: MarketType = MarketType.DAY_AHEAD
    ) -> MarketSession | None:
        stmt = select(MarketSession).where(
            MarketSession.market_date == market_date,
            MarketSession.market_type == market_type,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_by_status(self, status: MarketSessionStatus) -> Sequence[MarketSession]:
        stmt = (
            select(MarketSession)
            .where(MarketSession.status == status)
            .order_by(MarketSession.market_date.asc())
        )
        return self.session.execute(stmt).scalars().all()


class OrderRepository(BaseRepository[Order]):
    model = Order

    def list_active_for_session(
        self, market_session_id: UUID, side: OrderSide | None = None
    ) -> Sequence[Order]:
        """Orders in a session that still have energy to match.

        Ordered by price then arrival then id, giving the engine a stable
        sequence to tie-break on without having to sort defensively.
        `created_at` is the arrival time — price-time priority is the
        conventional fairness rule.
        """
        stmt = select(Order).where(
            Order.market_session_id == market_session_id,
            Order.status.in_(ACTIVE_ORDER_STATUSES),
        )
        if side is not None:
            stmt = stmt.where(Order.side == side)

        return (
            self.session.execute(
                stmt.order_by(
                    Order.created_at.asc(),
                    Order.id.asc(),
                )
            )
            .scalars()
            .all()
        )

    def list_for_user(self, user_id: UUID) -> Sequence[Order]:
        stmt = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
        return self.session.execute(stmt).scalars().all()

    def list_for_site(self, site_id: UUID) -> Sequence[Order]:
        stmt = select(Order).where(Order.site_id == site_id).order_by(Order.created_at.desc())
        return self.session.execute(stmt).scalars().all()


class TradeRepository(BaseRepository[Trade]):
    model = Trade

    def add_all(self, trades: Sequence[Trade]) -> Sequence[Trade]:
        """Stage many trades and flush once.

        A clearing is written as a unit; a per-row round trip would dominate
        its cost.
        """
        self.session.add_all(trades)
        self.session.flush()
        return trades

    def list_for_session(self, market_session_id: UUID) -> Sequence[Trade]:
        """Every trade produced by clearing a session."""
        buy = (
            select(Trade.id)
            .join(Order, Order.id == Trade.buy_order_id)
            .where(Order.market_session_id == market_session_id)
        )
        stmt = (
            select(Trade)
            .where(Trade.id.in_(buy))
            .order_by(Trade.delivery_start.asc(), Trade.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_for_order(self, order_id: UUID) -> Sequence[Trade]:
        stmt = (
            select(Trade)
            .where((Trade.buy_order_id == order_id) | (Trade.sell_order_id == order_id))
            .order_by(Trade.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()
