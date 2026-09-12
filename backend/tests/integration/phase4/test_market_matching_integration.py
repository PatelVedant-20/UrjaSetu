"""Integration test for BaselineMatchingEngine with market_service orchestration."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.enums import OrderSide, TradeStatus, UserRole
from app.domain.policies.market_matching import BaselineMatchingEngine
from app.services import market_service
from tests.integration.phase4.conftest import (
    DELIVERY_END,
    DELIVERY_START,
    MARKET_DATE,
    NOW,
)


def test_baseline_engine_full_market_clearing_integration(
    db_session: Session,
    make_tradeable_user: object,
) -> None:
    prosumer, prosumer_site = make_tradeable_user(role=UserRole.PROSUMER)  # type: ignore[operator]
    consumer, consumer_site = make_tradeable_user(role=UserRole.CONSUMER)  # type: ignore[operator]

    ms = market_service.open_session(db_session, market_date=MARKET_DATE, at=NOW)

    # Place Buy order: 15 kWh @ max 9.0 INR/kWh
    buy_order = market_service.place_order(
        db_session,
        market_session_id=ms.id,
        user_id=consumer.id,
        site_id=consumer_site.id,
        side=OrderSide.BUY,
        energy_kwh=Decimal("15.0"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        max_price_inr_per_kwh=Decimal("9.0"),
        at=NOW,
    )

    # Place Sell order directly to decouple from Phase 3 forecast surplus seeding
    from app.db.models import Order
    from app.domain.enums import OrderStatus

    sell_order = Order(
        market_session_id=ms.id,
        user_id=prosumer.id,
        site_id=prosumer_site.id,
        side=OrderSide.SELL,
        energy_kwh=Decimal("10.0"),
        min_price_inr_per_kwh=Decimal("5.0"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        status=OrderStatus.OPEN,
        created_at=NOW,
    )
    db_session.add(sell_order)
    db_session.flush()

    # Close session before clearing
    market_service.close_session(db_session, ms.id, at=NOW)

    # Clear session using real BaselineMatchingEngine
    engine = BaselineMatchingEngine()
    trades = market_service.clear_session(
        db_session,
        market_session_id=ms.id,
        engine=engine,
        at=NOW + timedelta(hours=1),
    )

    assert len(trades) == 1
    trade = trades[0]
    assert trade.buy_order_id == buy_order.id
    assert trade.sell_order_id == sell_order.id
    assert trade.quantity_kwh == Decimal("10.0")
    # Midpoint of 9.0 and 5.0 is 7.0000
    assert trade.clearing_price_inr_per_kwh == Decimal("7.0000")
    assert trade.status is TradeStatus.PROPOSED
    assert trade.matching_engine == "baseline_double_auction"
    assert trade.matching_engine_version == "0.1.0"

    # Verify orders updated in database
    db_session.refresh(buy_order)
    db_session.refresh(sell_order)
    assert sell_order.matched_kwh == Decimal("10.0000")
    assert sell_order.remaining_kwh == Decimal("0.0000")
    assert sell_order.status is OrderStatus.FILLED
    assert buy_order.matched_kwh == Decimal("10.0000")
    assert buy_order.remaining_kwh == Decimal("5.0000")
    assert buy_order.status is OrderStatus.PARTIALLY_FILLED
