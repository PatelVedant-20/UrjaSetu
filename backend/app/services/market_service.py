"""Market orchestration — sessions, orders, order book, clearing.

    orders -> OrderBook -> MatchingEngine -> proposed trades

Owns the transaction boundary for each market operation
(docs/04_DATA_MODEL.md, "Transaction Boundaries") and the sequencing around a
matching engine. It contains **no matching algorithm** and **no pricing
formula**: it builds a book, calls `engine.match(...)`, validates what comes
back, and persists it.

It also creates no second eligibility system. Whether a participant may trade
is decided by `app.domain.policies.eligibility` through
`app.services.identity_service`, and whether a seller has the energy is decided
by the Phase 3 surplus contract through `app.services.forecast_service`. Both
are consumed, never re-implemented.

Phase 4 produces *candidates*. docs/05_API_SPEC.md: clearing "does not silently
bypass grid validation", so every trade this module writes is `proposed`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.db.models.market import MarketSession, Order, Trade
from app.domain.enums import (
    MarketSessionStatus,
    MarketType,
    OrderSide,
    OrderStatus,
    RealtimeEventType,
    TradeStatus,
)
from app.domain.interfaces.market import (
    MatchingEngine,
    MatchingRequest,
    MatchingResult,
    OrderBook,
    OrderBookEntry,
)
from app.domain.interfaces.realtime import RealtimeEvent, scalar
from app.repositories import (
    MarketSessionRepository,
    OrderRepository,
    SiteRepository,
    TradeRepository,
)
from app.services import audit_service, forecast_service, identity_service
from app.services.realtime_service import publish as notify

ZERO = Decimal("0")


class MarketStateError(ConflictError):
    """An operation is not legal in the session's or order's current state."""

    code = "MARKET_STATE_INVALID"


class OrderValidationError(UnprocessableError):
    """An order cannot be accepted as submitted."""

    code = "ORDER_VALIDATION_FAILED"


class MatchingEngineError(UnprocessableError):
    """An engine failed, or returned a result the contract does not allow."""

    code = "MATCHING_ENGINE_FAILED"


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def open_session(
    session: Session,
    *,
    market_date: date,
    market_type: MarketType = MarketType.DAY_AHEAD,
    at: datetime | None = None,
) -> MarketSession:
    """Create and open a market session for a trading date."""
    repo = MarketSessionRepository(session)
    if repo.get_for_date(market_date, market_type) is not None:
        raise MarketStateError(
            "A market session already exists for this date and type.",
            code="MARKET_SESSION_ALREADY_EXISTS",
            details={"market_date": market_date.isoformat(), "market_type": market_type.value},
        )

    market_session = MarketSession(
        market_date=market_date,
        market_type=market_type,
        status=MarketSessionStatus.OPEN,
        opened_at=at or datetime.now(UTC),
    )
    repo.add(market_session)
    session.commit()
    session.refresh(market_session)
    return market_session


def get_session(session: Session, market_session_id: UUID) -> MarketSession:
    market_session = MarketSessionRepository(session).get(market_session_id)
    if market_session is None:
        raise NotFoundError(
            "Market session not found.",
            code="MARKET_SESSION_NOT_FOUND",
            details={"id": str(market_session_id)},
        )
    return market_session


def close_session(
    session: Session, market_session_id: UUID, *, at: datetime | None = None
) -> MarketSession:
    """Stop taking orders.

    Clearing an open session would match against a book that is still
    changing, so intake closes first and clearing is a separate step.
    """
    market_session = get_session(session, market_session_id)
    if market_session.status is not MarketSessionStatus.OPEN:
        raise MarketStateError(
            f"A {market_session.status.value} session cannot be closed.",
            details={"status": market_session.status.value},
        )

    market_session.status = MarketSessionStatus.CLOSED
    market_session.closed_at = at or datetime.now(UTC)
    session.commit()
    session.refresh(market_session)
    return market_session


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def place_order(
    session: Session,
    *,
    market_session_id: UUID,
    user_id: UUID,
    site_id: UUID,
    side: OrderSide,
    energy_kwh: Decimal,
    delivery_start: datetime,
    delivery_end: datetime,
    max_price_inr_per_kwh: Decimal | None = None,
    min_price_inr_per_kwh: Decimal | None = None,
    node_id: UUID | None = None,
    forecast_basis_id: UUID | None = None,
    reliability_score_snapshot: Decimal | None = None,
    at: datetime | None = None,
) -> Order:
    """Validate and record a buy or sell intent. One transaction.

    Validation order matters: actor eligibility first, then the order's own
    shape, then — for a sell — whether the forecast says the energy exists.
    """
    market_session = get_session(session, market_session_id)
    if not market_session.status.accepts_orders:
        raise MarketStateError(
            f"A {market_session.status.value} session does not accept orders.",
            details={"status": market_session.status.value},
        )

    if SiteRepository(session).get(site_id) is None:
        raise NotFoundError("Site not found.", code="SITE_NOT_FOUND", details={"id": str(site_id)})

    _require_eligibility(session, user_id, side)
    _validate_order_shape(
        side=side,
        energy_kwh=energy_kwh,
        delivery_start=delivery_start,
        delivery_end=delivery_end,
        max_price_inr_per_kwh=max_price_inr_per_kwh,
        min_price_inr_per_kwh=min_price_inr_per_kwh,
    )
    if side is OrderSide.SELL:
        _require_forecast_surplus(
            session,
            site_id,
            energy_kwh=energy_kwh,
            delivery_start=delivery_start,
            delivery_end=delivery_end,
        )

    order = Order(
        market_session_id=market_session_id,
        user_id=user_id,
        site_id=site_id,
        node_id=node_id,
        side=side,
        energy_kwh=energy_kwh,
        min_price_inr_per_kwh=min_price_inr_per_kwh,
        max_price_inr_per_kwh=max_price_inr_per_kwh,
        delivery_start=delivery_start,
        delivery_end=delivery_end,
        forecast_basis_id=forecast_basis_id,
        reliability_score_snapshot=reliability_score_snapshot,
        status=OrderStatus.OPEN,
        matched_kwh=ZERO,
        created_at=at or datetime.now(UTC),
    )
    OrderRepository(session).add(order)
    session.flush()
    audit_service.record(
        session,
        audit_service.order_placed(
            order_id=order.id,
            user_id=order.user_id,
            site_id=order.site_id,
            side=order.side.value,
            energy_kwh=order.energy_kwh,
            limit_price_inr_per_kwh=(
                order.max_price_inr_per_kwh
                if order.side is OrderSide.BUY
                else order.min_price_inr_per_kwh
            ),
            delivery_start=order.delivery_start,
            delivery_end=order.delivery_end,
            occurred_at=order.created_at or datetime.now(UTC),
        ),
    )
    session.commit()
    session.refresh(order)

    # After the commit, never before: a notification that sent a client to
    # refetch an order that did not exist yet would be worse than no
    # notification at all.
    notify(
        RealtimeEvent(
            event_type=RealtimeEventType.ORDER_ACCEPTED,
            entity_type="order",
            entity_id=order.id,
            payload={
                "market_session_id": scalar(order.market_session_id),
                "side": scalar(order.side),
                "energy_kwh": scalar(order.energy_kwh),
                "status": scalar(order.status),
            },
        )
    )
    return order


def get_order(session: Session, order_id: UUID) -> Order:
    order = OrderRepository(session).get(order_id)
    if order is None:
        raise NotFoundError(
            "Order not found.", code="ORDER_NOT_FOUND", details={"id": str(order_id)}
        )
    return order


def cancel_order(session: Session, order_id: UUID) -> Order:
    """Withdraw an order that has not been fully matched.

    A matched order cannot be cancelled: the energy is already committed to a
    proposed trade, and unwinding that is a Phase 7 concern, not a withdrawal.
    """
    order = get_order(session, order_id)
    if not order.status.is_active:
        raise MarketStateError(
            f"A {order.status.value} order cannot be cancelled.",
            details={"status": order.status.value},
        )

    order.status = OrderStatus.CANCELLED
    session.commit()
    session.refresh(order)
    return order


# ---------------------------------------------------------------------------
# Order book
# ---------------------------------------------------------------------------


def build_order_book(session: Session, market_session_id: UUID) -> OrderBook:
    """Project a session's active orders into the matching contract.

    Persistence models are deliberately not handed to an engine: it receives
    plain values, so it cannot lazy-load a relationship or reach the database
    mid-match.
    """
    market_session = get_session(session, market_session_id)
    orders = OrderRepository(session).list_active_for_session(market_session_id)

    entries = [_to_entry(order) for order in orders]
    return OrderBook(
        market_session_id=market_session.id,
        market_date=market_session.market_date,
        market_type=market_session.market_type,
        buys=tuple(e for e in entries if e.side is OrderSide.BUY),
        sells=tuple(e for e in entries if e.side is OrderSide.SELL),
    )


# ---------------------------------------------------------------------------
# Clearing
# ---------------------------------------------------------------------------


def clear_session(
    session: Session,
    market_session_id: UUID,
    *,
    engine: MatchingEngine,
    at: datetime | None = None,
) -> Sequence[Trade]:
    """Run matching and record the proposed trades. One transaction.

    The engine is passed in rather than imported, so this function stays
    ignorant of which algorithm exists. Its output is validated at the boundary
    before anything is written.
    """
    market_session = get_session(session, market_session_id)
    if not market_session.status.can_clear:
        raise MarketStateError(
            f"A {market_session.status.value} session cannot be cleared.",
            details={"status": market_session.status.value},
        )

    cleared_at = at or datetime.now(UTC)

    # The one notification published before the transaction, because it claims
    # no persisted state: it says clearing has begun, which is already true.
    # Sent after the status check, so it is never emitted for a session that
    # cannot clear.
    notify(
        RealtimeEvent(
            event_type=RealtimeEventType.CLEARING_STARTED,
            entity_type="market_session",
            entity_id=market_session.id,
            payload={
                "market_date": scalar(market_session.market_date.isoformat()),
                "engine": scalar(engine.name),
            },
        )
    )

    book = build_order_book(session, market_session_id)
    request = MatchingRequest(order_book=book, cleared_at=cleared_at)

    try:
        result = engine.match(request)
    except Exception as exc:
        raise MatchingEngineError(
            f"Matching engine {engine.name!r} failed to clear the session.",
            details={"engine": engine.name, "reason": exc.__class__.__name__},
        ) from exc

    _validate_result(result, book, engine)

    orders = {
        order.id: order
        for order in OrderRepository(session).list_active_for_session(market_session_id)
    }
    trades = [
        Trade(
            buy_order_id=proposed.buy_order_id,
            sell_order_id=proposed.sell_order_id,
            quantity_kwh=proposed.quantity_kwh,
            clearing_price_inr_per_kwh=proposed.clearing_price_inr_per_kwh,
            delivery_start=proposed.delivery_start,
            delivery_end=proposed.delivery_end,
            status=TradeStatus.PROPOSED,
            matching_engine=result.engine,
            matching_engine_version=result.engine_version,
        )
        for proposed in result.trades
    ]
    TradeRepository(session).add_all(trades)

    for proposed in result.trades:
        for order_id in (proposed.buy_order_id, proposed.sell_order_id):
            _apply_fill(orders[order_id], proposed.quantity_kwh)

    market_session.status = MarketSessionStatus.CLEARED
    market_session.cleared_at = cleared_at
    session.flush()

    audit_service.record(
        session,
        audit_service.market_cleared(
            market_session_id=market_session.id,
            market_date=market_session.market_date.isoformat(),
            trade_count=len(trades),
            matched_kwh=result.matched_kwh,
            matching_engine=result.engine,
            matching_engine_version=result.engine_version,
            occurred_at=cleared_at,
        ),
    )

    for trade in trades:
        audit_service.record(
            session,
            audit_service.trade_proposed(
                trade_id=trade.id,
                buy_order_id=trade.buy_order_id,
                sell_order_id=trade.sell_order_id,
                quantity_kwh=trade.quantity_kwh,
                clearing_price_inr_per_kwh=trade.clearing_price_inr_per_kwh,
                delivery_start=trade.delivery_start,
                delivery_end=trade.delivery_end,
                occurred_at=trade.created_at or cleared_at,
            ),
        )

    session.commit()

    for trade in trades:
        notify(
            RealtimeEvent(
                event_type=RealtimeEventType.TRADE_PROPOSED,
                entity_type="trade",
                entity_id=trade.id,
                trade_id=trade.id,
                payload={
                    "market_session_id": scalar(market_session_id),
                    "quantity_kwh": scalar(trade.quantity_kwh),
                    "clearing_price_inr_per_kwh": scalar(trade.clearing_price_inr_per_kwh),
                    "status": scalar(trade.status),
                },
            )
        )
    return trades


def get_trade(session: Session, trade_id: UUID) -> Trade:
    trade = TradeRepository(session).get(trade_id)
    if trade is None:
        raise NotFoundError(
            "Trade not found.", code="TRADE_NOT_FOUND", details={"id": str(trade_id)}
        )
    return trade


def list_trades_for_session(session: Session, market_session_id: UUID) -> Sequence[Trade]:
    get_session(session, market_session_id)
    return TradeRepository(session).list_for_session(market_session_id)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _to_entry(order: Order) -> OrderBookEntry:
    return OrderBookEntry(
        order_id=order.id,
        side=order.side,
        user_id=order.user_id,
        site_id=order.site_id,
        node_id=order.node_id,
        remaining_kwh=order.remaining_kwh,
        delivery_start=order.delivery_start,
        delivery_end=order.delivery_end,
        created_at=order.created_at,
        max_price_inr_per_kwh=order.max_price_inr_per_kwh,
        min_price_inr_per_kwh=order.min_price_inr_per_kwh,
        reliability_score_snapshot=order.reliability_score_snapshot,
    )


def _apply_fill(order: Order, quantity_kwh: Decimal) -> None:
    """Record energy committed to a proposed trade."""
    order.matched_kwh = order.matched_kwh + quantity_kwh
    order.status = (
        OrderStatus.FILLED
        if order.matched_kwh >= order.energy_kwh
        else OrderStatus.PARTIALLY_FILLED
    )


def _require_eligibility(session: Session, user_id: UUID, side: OrderSide) -> None:
    """Defer to the existing eligibility policy.

    Phase 1 already decides who may trade; re-deriving it here would create a
    second answer to the same question.
    """
    decision, _ = identity_service.get_eligibility(session, user_id)
    permitted = decision.can_sell if side is OrderSide.SELL else decision.can_buy
    if not permitted:
        raise OrderValidationError(
            f"User is not eligible to {side.value}.",
            code="USER_NOT_ELIGIBLE",
            details={"side": side.value, "reasons": list(decision.reasons)},
        )


def _require_forecast_surplus(
    session: Session,
    site_id: UUID,
    *,
    energy_kwh: Decimal,
    delivery_start: datetime,
    delivery_end: datetime,
) -> None:
    """A sell must be backed by forecast surplus.

    Consumes the Phase 3 contract rather than recomputing it: selling energy a
    site is not expected to have is how a market ends up unable to deliver
    (docs/01_FINAL_ARCHITECTURE.md: forecast under-delivery).
    """
    window = forecast_service.get_surplus_for_site(
        session, site_id, start=delivery_start, end=delivery_end
    )
    available = window.total_exportable_kwh
    if available < energy_kwh:
        raise OrderValidationError(
            "Sell quantity exceeds eligible available energy.",
            code="INSUFFICIENT_FORECAST_SURPLUS",
            details={
                "requested_kwh": str(energy_kwh),
                "available_kwh": str(available),
            },
        )


def _validate_order_shape(
    *,
    side: OrderSide,
    energy_kwh: Decimal,
    delivery_start: datetime,
    delivery_end: datetime,
    max_price_inr_per_kwh: Decimal | None,
    min_price_inr_per_kwh: Decimal | None,
) -> None:
    """The constraints docs/04_DATA_MODEL.md entity 14 lists by example.

    Checked here so a caller gets a named domain error, and again by the
    database so no other path can write an order that breaks them.
    """
    if energy_kwh <= ZERO:
        raise OrderValidationError(
            "energy_kwh must be greater than zero.", code="ORDER_QUANTITY_INVALID"
        )
    if delivery_end <= delivery_start:
        raise OrderValidationError(
            "delivery_end must be after delivery_start.", code="ORDER_WINDOW_INVALID"
        )
    if side is OrderSide.BUY and max_price_inr_per_kwh is None:
        raise OrderValidationError(
            "A buy order requires max_price_inr_per_kwh.", code="ORDER_PRICE_REQUIRED"
        )
    if side is OrderSide.SELL and min_price_inr_per_kwh is None:
        raise OrderValidationError(
            "A sell order requires min_price_inr_per_kwh.", code="ORDER_PRICE_REQUIRED"
        )


def _validate_result(result: MatchingResult, book: OrderBook, engine: MatchingEngine) -> None:
    """Check an engine's output before trusting it.

    Enforced at the boundary rather than assumed, so a misbehaving engine
    produces a clear, attributable error instead of silently over-selling a
    participant's energy.
    """
    known = {entry.order_id: entry for entry in (*book.buys, *book.sells)}
    committed: dict[UUID, Decimal] = {}

    for trade in result.trades:
        for order_id, expected_side in (
            (trade.buy_order_id, OrderSide.BUY),
            (trade.sell_order_id, OrderSide.SELL),
        ):
            entry = known.get(order_id)
            if entry is None:
                raise MatchingEngineError(
                    "Engine proposed a trade referencing an order outside the book.",
                    details={"engine": engine.name, "order_id": str(order_id)},
                )
            if entry.side is not expected_side:
                raise MatchingEngineError(
                    "Engine paired an order on the wrong side of the trade.",
                    details={"engine": engine.name, "order_id": str(order_id)},
                )
            committed[order_id] = committed.get(order_id, ZERO) + trade.quantity_kwh

        if trade.quantity_kwh <= ZERO:
            raise MatchingEngineError(
                "Engine proposed a non-positive trade quantity.",
                details={"engine": engine.name, "quantity_kwh": str(trade.quantity_kwh)},
            )
        if trade.clearing_price_inr_per_kwh < ZERO:
            raise MatchingEngineError(
                "Engine proposed a negative clearing price.",
                details={"engine": engine.name},
            )
        if trade.delivery_end <= trade.delivery_start:
            raise MatchingEngineError(
                "Engine proposed a trade whose delivery window is empty.",
                details={"engine": engine.name},
            )

    for order_id, total in committed.items():
        if total > known[order_id].remaining_kwh:
            raise MatchingEngineError(
                "Engine over-filled an order beyond its remaining energy.",
                details={
                    "engine": engine.name,
                    "order_id": str(order_id),
                    "committed_kwh": str(total),
                    "remaining_kwh": str(known[order_id].remaining_kwh),
                },
            )
