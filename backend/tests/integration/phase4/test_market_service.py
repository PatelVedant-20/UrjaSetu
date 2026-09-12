"""Phase 4 gate: orders -> order book -> matching -> proposed trades.

Exercises the orchestration layer against real PostgreSQL using stand-in
engines. No matching algorithm is tested here — that is the engine's own
business, and the point of the boundary is that this layer cannot tell the
difference.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.db.models import Site, User
from app.domain.enums import (
    MarketSessionStatus,
    OrderSide,
    OrderStatus,
    TradeStatus,
    UserRole,
)
from app.services import market_service
from tests.integration.phase4.conftest import (
    DELIVERY_END,
    DELIVERY_START,
    MARKET_DATE,
    NOW,
    FailingMatchingEngine,
    MisbehavingMatchingEngine,
    StubMatchingEngine,
)


def _open(db_session: Session, market_date: date = MARKET_DATE):  # type: ignore[no-untyped-def]
    return market_service.open_session(db_session, market_date=market_date, at=NOW)


def _buy(db_session: Session, ms_id, user, site, **kw):  # type: ignore[no-untyped-def]
    defaults = {
        "market_session_id": ms_id,
        "user_id": user.id,
        "site_id": site.id,
        "side": OrderSide.BUY,
        "energy_kwh": Decimal("10.0"),
        "delivery_start": DELIVERY_START,
        "delivery_end": DELIVERY_END,
        "max_price_inr_per_kwh": Decimal("8.0"),
        "at": NOW,
    }
    return market_service.place_order(db_session, **{**defaults, **kw})


def _sell(db_session: Session, ms_id, user, site, **kw):  # type: ignore[no-untyped-def]
    defaults = {
        "market_session_id": ms_id,
        "user_id": user.id,
        "site_id": site.id,
        "side": OrderSide.SELL,
        "energy_kwh": Decimal("10.0"),
        "delivery_start": DELIVERY_START,
        "delivery_end": DELIVERY_END,
        "min_price_inr_per_kwh": Decimal("6.0"),
        "at": NOW,
    }
    return market_service.place_order(db_session, **{**defaults, **kw})


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_open_session(db_session: Session) -> None:
    ms = _open(db_session)

    assert ms.status is MarketSessionStatus.OPEN
    assert ms.market_date == MARKET_DATE
    assert ms.opened_at == NOW


def test_a_second_session_for_the_same_date_is_refused(db_session: Session) -> None:
    _open(db_session)

    with pytest.raises(ConflictError) as exc:
        _open(db_session)

    assert exc.value.code == "MARKET_SESSION_ALREADY_EXISTS"


def test_close_session_stops_intake(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)

    closed = market_service.close_session(db_session, ms.id, at=NOW)
    assert closed.status is MarketSessionStatus.CLOSED

    with pytest.raises(ConflictError) as exc:
        _buy(db_session, ms.id, user, site)
    assert exc.value.code == "MARKET_STATE_INVALID"


def test_closing_twice_is_refused(db_session: Session) -> None:
    ms = _open(db_session)
    market_service.close_session(db_session, ms.id, at=NOW)

    with pytest.raises(ConflictError):
        market_service.close_session(db_session, ms.id, at=NOW)


def test_unknown_session_is_reported(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc:
        market_service.get_session(db_session, uuid.uuid4())

    assert exc.value.code == "MARKET_SESSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def test_place_buy_order(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)

    order = _buy(db_session, ms.id, user, site)

    assert order.side is OrderSide.BUY
    assert order.status is OrderStatus.OPEN
    assert order.remaining_kwh == Decimal("10.0000")


def test_order_uses_the_existing_eligibility_policy(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """No second eligibility system: an unverified user is refused."""
    ms = _open(db_session)
    user = make_user(role=UserRole.CONSUMER)
    site = make_site(owner_user_id=user.id)

    with pytest.raises(UnprocessableError) as exc:
        _buy(db_session, ms.id, user, site)

    assert exc.value.code == "USER_NOT_ELIGIBLE"
    # The refusal carries the policy's own reasons, not a re-derived list.
    assert exc.value.details["reasons"]


def test_observer_roles_cannot_place_orders(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.REGULATOR_VIEWER)

    with pytest.raises(UnprocessableError) as exc:
        _buy(db_session, ms.id, user, site)

    assert exc.value.code == "USER_NOT_ELIGIBLE"


def test_buy_without_a_max_price_is_refused(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)

    with pytest.raises(UnprocessableError) as exc:
        _buy(db_session, ms.id, user, site, max_price_inr_per_kwh=None)

    assert exc.value.code == "ORDER_PRICE_REQUIRED"


def test_non_positive_quantity_is_refused(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)

    with pytest.raises(UnprocessableError) as exc:
        _buy(db_session, ms.id, user, site, energy_kwh=Decimal("0"))

    assert exc.value.code == "ORDER_QUANTITY_INVALID"


def test_empty_delivery_window_is_refused(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)

    with pytest.raises(UnprocessableError) as exc:
        _buy(db_session, ms.id, user, site, delivery_end=DELIVERY_START)

    assert exc.value.code == "ORDER_WINDOW_INVALID"


def test_sell_without_forecast_surplus_is_refused(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    """Selling energy the forecast does not predict is how a market fails to deliver.

    Consumes the Phase 3 surplus contract rather than recomputing it.
    """
    ms = _open(db_session)
    user, site = make_tradeable_user()

    with pytest.raises(UnprocessableError) as exc:
        _sell(db_session, ms.id, user, site)

    assert exc.value.code == "INSUFFICIENT_FORECAST_SURPLUS"
    assert exc.value.details["available_kwh"] == "0"


def test_unknown_site_is_reported(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, _ = make_tradeable_user(role=UserRole.CONSUMER)

    with pytest.raises(NotFoundError) as exc:
        market_service.place_order(
            db_session,
            market_session_id=ms.id,
            user_id=user.id,
            site_id=uuid.uuid4(),
            side=OrderSide.BUY,
            energy_kwh=Decimal("1"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            max_price_inr_per_kwh=Decimal("8"),
            at=NOW,
        )

    assert exc.value.code == "SITE_NOT_FOUND"


def test_cancel_order(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)
    order = _buy(db_session, ms.id, user, site)

    cancelled = market_service.cancel_order(db_session, order.id)

    assert cancelled.status is OrderStatus.CANCELLED
    # Cancelling twice is not legal.
    with pytest.raises(ConflictError):
        market_service.cancel_order(db_session, order.id)


# ---------------------------------------------------------------------------
# Order book
# ---------------------------------------------------------------------------


def test_order_book_projects_active_orders(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    buyer, buyer_site = make_tradeable_user(role=UserRole.CONSUMER)
    _buy(db_session, ms.id, buyer, buyer_site)

    book = market_service.build_order_book(db_session, ms.id)

    assert book.market_session_id == ms.id
    assert len(book.buys) == 1
    assert book.total_demand_kwh == Decimal("10.0000")
    # A one-sided book cannot clear.
    assert book.is_empty is True


def test_cancelled_orders_leave_the_book(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)
    order = _buy(db_session, ms.id, user, site)
    market_service.cancel_order(db_session, order.id)

    assert market_service.build_order_book(db_session, ms.id).buys == ()


def test_book_carries_no_persistence_objects(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    """An engine must not be handed something that can reach the database."""
    ms = _open(db_session)
    user, site = make_tradeable_user(role=UserRole.CONSUMER)
    _buy(db_session, ms.id, user, site)

    entry = market_service.build_order_book(db_session, ms.id).buys[0]

    assert not hasattr(entry, "_sa_instance_state")
    assert isinstance(entry.order_id, uuid.UUID)


# ---------------------------------------------------------------------------
# Clearing
# ---------------------------------------------------------------------------


def _crossing_book(db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]):  # type: ignore[no-untyped-def]
    """A session with one buy and one sell that cross in price and time."""
    from app.db.models import Order

    ms = _open(db_session)
    buyer, buyer_site = make_tradeable_user(role=UserRole.CONSUMER)
    seller, seller_site = make_tradeable_user()
    buy = _buy(db_session, ms.id, buyer, buyer_site)
    # Inserted directly: the surplus guard is exercised separately, and this
    # test is about clearing, not about order admission.
    sell = Order(
        market_session_id=ms.id,
        user_id=seller.id,
        site_id=seller_site.id,
        side=OrderSide.SELL,
        energy_kwh=Decimal("10.0"),
        min_price_inr_per_kwh=Decimal("6.0"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        status=OrderStatus.OPEN,
        created_at=NOW,
    )
    db_session.add(sell)
    db_session.flush()
    market_service.close_session(db_session, ms.id, at=NOW)
    return ms, buy, sell


def test_clearing_produces_proposed_trades(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    """The gate: orders -> book -> matching -> proposed trades."""
    ms, buy, sell = _crossing_book(db_session, make_tradeable_user)
    engine = StubMatchingEngine()

    trades = market_service.clear_session(db_session, ms.id, engine=engine, at=NOW)

    assert len(trades) == 1
    trade = trades[0]
    # Phase 4 proposes; it never approves or commits.
    assert trade.status is TradeStatus.PROPOSED
    assert trade.quantity_kwh == Decimal("10.0000")
    # Midpoint of the 8.00 ceiling and 6.00 floor.
    assert trade.clearing_price_inr_per_kwh == Decimal("7.0000")
    assert trade.matching_engine == "stub"
    assert trade.matching_engine_version == "1.0.0"

    db_session.refresh(buy)
    db_session.refresh(sell)
    assert buy.status is OrderStatus.FILLED
    assert sell.status is OrderStatus.FILLED
    assert market_service.get_session(db_session, ms.id).status is MarketSessionStatus.CLEARED


def test_service_does_not_know_which_engine_it_called(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    """Two unrelated engines drive the same orchestration unchanged."""
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)

    trades = market_service.clear_session(
        db_session,
        ms.id,
        engine=StubMatchingEngine(name="optimiser", engine_version="9.9"),
        at=NOW,
    )

    assert trades[0].matching_engine == "optimiser"
    assert trades[0].matching_engine_version == "9.9"


def test_engine_receives_the_book_and_the_clearing_instant(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)
    engine = StubMatchingEngine()

    market_service.clear_session(db_session, ms.id, engine=engine, at=NOW)

    request = engine.calls[0]
    assert request.market_session_id == ms.id
    assert request.cleared_at == NOW
    assert len(request.order_book.buys) == 1
    assert len(request.order_book.sells) == 1


def test_partial_fill_leaves_the_remainder_open(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    from app.db.models import Order

    ms = _open(db_session)
    buyer, buyer_site = make_tradeable_user(role=UserRole.CONSUMER)
    seller, seller_site = make_tradeable_user()
    buy = _buy(db_session, ms.id, buyer, buyer_site, energy_kwh=Decimal("10"))
    db_session.add(
        Order(
            market_session_id=ms.id,
            user_id=seller.id,
            site_id=seller_site.id,
            side=OrderSide.SELL,
            energy_kwh=Decimal("4"),
            min_price_inr_per_kwh=Decimal("6.0"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            status=OrderStatus.OPEN,
            created_at=NOW,
        )
    )
    db_session.flush()
    market_service.close_session(db_session, ms.id, at=NOW)

    trades = market_service.clear_session(db_session, ms.id, engine=StubMatchingEngine(), at=NOW)

    assert trades[0].quantity_kwh == Decimal("4.0000")
    db_session.refresh(buy)
    assert buy.status is OrderStatus.PARTIALLY_FILLED
    assert buy.remaining_kwh == Decimal("6.0000")


def test_an_open_session_cannot_be_cleared(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    """Clearing an open book would match against orders that are still arriving."""
    ms = _open(db_session)

    with pytest.raises(ConflictError) as exc:
        market_service.clear_session(db_session, ms.id, engine=StubMatchingEngine(), at=NOW)

    assert exc.value.code == "MARKET_STATE_INVALID"


def test_a_session_cannot_be_cleared_twice(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    """Double clearing would commit the same energy twice."""
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)
    market_service.clear_session(db_session, ms.id, engine=StubMatchingEngine(), at=NOW)

    with pytest.raises(ConflictError):
        market_service.clear_session(db_session, ms.id, engine=StubMatchingEngine(), at=NOW)


def test_engine_failure_is_reported_not_swallowed(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)

    with pytest.raises(UnprocessableError) as exc:
        market_service.clear_session(db_session, ms.id, engine=FailingMatchingEngine(), at=NOW)

    assert exc.value.code == "MATCHING_ENGINE_FAILED"


@pytest.mark.parametrize(
    "mode",
    ["over_fill", "unknown_order", "wrong_side", "zero_quantity", "negative_price", "empty_window"],
)
def test_contract_violations_are_rejected(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]], mode: str
) -> None:
    """An engine's output is checked at the boundary, never assumed."""
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)

    with pytest.raises(UnprocessableError) as exc:
        market_service.clear_session(
            db_session, ms.id, engine=MisbehavingMatchingEngine(mode=mode), at=NOW
        )

    assert exc.value.code == "MATCHING_ENGINE_FAILED"


def test_no_trades_are_written_when_an_engine_misbehaves(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)

    with pytest.raises(UnprocessableError):
        market_service.clear_session(
            db_session, ms.id, engine=MisbehavingMatchingEngine(mode="over_fill"), at=NOW
        )

    # Validation runs before anything is staged, so nothing needs unwinding.
    assert market_service.list_trades_for_session(db_session, ms.id) == []
    assert market_service.get_session(db_session, ms.id).status is MarketSessionStatus.CLOSED


def test_clearing_is_deterministic(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    """Same book, same engine, same trades — required by docs/10."""
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)
    book = market_service.build_order_book(db_session, ms.id)
    from app.domain.interfaces.market import MatchingRequest

    engine = StubMatchingEngine()
    first = engine.match(MatchingRequest(order_book=book, cleared_at=NOW))
    second = engine.match(MatchingRequest(order_book=book, cleared_at=NOW))

    assert [(t.buy_order_id, t.sell_order_id, t.quantity_kwh) for t in first.trades] == [
        (t.buy_order_id, t.sell_order_id, t.quantity_kwh) for t in second.trades
    ]


def test_trade_lookup(
    db_session: Session, make_tradeable_user: Callable[..., tuple[User, Site]]
) -> None:
    ms, _, _ = _crossing_book(db_session, make_tradeable_user)
    trades = market_service.clear_session(db_session, ms.id, engine=StubMatchingEngine(), at=NOW)

    assert market_service.get_trade(db_session, trades[0].id).id == trades[0].id
    assert len(market_service.list_trades_for_session(db_session, ms.id)) == 1

    with pytest.raises(NotFoundError) as exc:
        market_service.get_trade(db_session, uuid.uuid4())
    assert exc.value.code == "TRADE_NOT_FOUND"
