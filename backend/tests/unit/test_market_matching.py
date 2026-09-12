"""Unit tests for BaselineMatchingEngine and merit-order matching policy.

Tests the canonical MatchingEngine interface against:
- one match
- no match
- partial fill (buyer or seller partially filled)
- multiple sellers (merit order price asc)
- multiple buyers (merit order price desc)
- price incompatibility (seller floor > buyer ceiling)
- time incompatibility (disjoint delivery windows)
- deterministic ties (price tie -> created_at -> order_id)
- cancelled / zero remaining quantity orders
- empty book (no buyers, no sellers, or both empty)
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.domain.enums import MarketType, OrderSide
from app.domain.interfaces.market import (
    ZERO,
    MatchingEngine,
    MatchingRequest,
    OrderBook,
    OrderBookEntry,
)
from app.domain.policies.market_matching import (
    BaselineMatchingEngine,
    ContinuousDoubleAuctionMatchingEngine,
)

T0 = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _entry(side: OrderSide, **overrides: object) -> OrderBookEntry:
    defaults: dict[str, object] = {
        "order_id": uuid4(),
        "side": side,
        "user_id": uuid4(),
        "site_id": uuid4(),
        "remaining_kwh": Decimal("10"),
        "delivery_start": T0,
        "delivery_end": T0 + HOUR,
        "created_at": T0 - HOUR,
    }
    if side is OrderSide.BUY:
        defaults["max_price_inr_per_kwh"] = Decimal("8")
    else:
        defaults["min_price_inr_per_kwh"] = Decimal("6")
    return OrderBookEntry(**{**defaults, **overrides})  # type: ignore[arg-type]


def _request(
    buys: tuple[OrderBookEntry, ...] = (), sells: tuple[OrderBookEntry, ...] = ()
) -> MatchingRequest:
    book = OrderBook(
        market_session_id=uuid4(),
        market_date=date(2026, 6, 2),
        market_type=MarketType.DAY_AHEAD,
        buys=buys,
        sells=sells,
    )
    return MatchingRequest(order_book=book, cleared_at=T0)


def test_engine_protocol_conformance() -> None:
    engine = BaselineMatchingEngine()
    assert isinstance(engine, MatchingEngine)
    assert engine.name == "baseline_double_auction"
    assert engine.engine_version == "0.1.0"
    assert ContinuousDoubleAuctionMatchingEngine is BaselineMatchingEngine


def test_empty_book_returns_no_trades() -> None:
    engine = BaselineMatchingEngine()

    # 1. Both empty
    req_empty = _request(buys=(), sells=())
    res_empty = engine.match(req_empty)
    assert res_empty.trade_count == 0
    assert res_empty.matched_kwh == ZERO

    # 2. Buys only
    buy = _entry(OrderSide.BUY)
    req_buys_only = _request(buys=(buy,), sells=())
    res_buys_only = engine.match(req_buys_only)
    assert res_buys_only.trade_count == 0
    assert res_buys_only.unmatched_buy_order_ids == (buy.order_id,)

    # 3. Sells only
    sell = _entry(OrderSide.SELL)
    req_sells_only = _request(buys=(), sells=(sell,))
    res_sells_only = engine.match(req_sells_only)
    assert res_sells_only.trade_count == 0
    assert res_sells_only.unmatched_sell_order_ids == (sell.order_id,)


def test_one_exact_match() -> None:
    engine = BaselineMatchingEngine()
    buy = _entry(OrderSide.BUY, remaining_kwh=Decimal("10"), max_price_inr_per_kwh=Decimal("8"))
    sell = _entry(OrderSide.SELL, remaining_kwh=Decimal("10"), min_price_inr_per_kwh=Decimal("6"))

    req = _request(buys=(buy,), sells=(sell,))
    res = engine.match(req)

    assert res.trade_count == 1
    assert res.matched_kwh == Decimal("10")
    assert len(res.unmatched_buy_order_ids) == 0
    assert len(res.unmatched_sell_order_ids) == 0

    trade = res.trades[0]
    assert trade.buy_order_id == buy.order_id
    assert trade.sell_order_id == sell.order_id
    assert trade.quantity_kwh == Decimal("10")
    # Midpoint of 8 and 6 is 7.0000
    assert trade.clearing_price_inr_per_kwh == Decimal("7.0000")
    assert trade.delivery_start == T0
    assert trade.delivery_end == T0 + HOUR


def test_no_match_due_to_price_incompatibility() -> None:
    engine = BaselineMatchingEngine()
    # Buyer willing to pay at most 5.0, seller demands at least 7.0
    buy = _entry(OrderSide.BUY, max_price_inr_per_kwh=Decimal("5.0"))
    sell = _entry(OrderSide.SELL, min_price_inr_per_kwh=Decimal("7.0"))

    req = _request(buys=(buy,), sells=(sell,))
    res = engine.match(req)

    assert res.trade_count == 0
    assert res.matched_kwh == ZERO
    assert res.unmatched_buy_order_ids == (buy.order_id,)
    assert res.unmatched_sell_order_ids == (sell.order_id,)


def test_no_match_due_to_time_incompatibility() -> None:
    engine = BaselineMatchingEngine()
    # Non-overlapping delivery windows
    buy = _entry(
        OrderSide.BUY,
        delivery_start=T0,
        delivery_end=T0 + HOUR,
    )
    sell = _entry(
        OrderSide.SELL,
        delivery_start=T0 + HOUR,
        delivery_end=T0 + (2 * HOUR),
    )

    req = _request(buys=(buy,), sells=(sell,))
    res = engine.match(req)

    assert res.trade_count == 0
    assert res.matched_kwh == ZERO
    assert res.unmatched_buy_order_ids == (buy.order_id,)
    assert res.unmatched_sell_order_ids == (sell.order_id,)


def test_partial_fill_buyer_larger() -> None:
    engine = BaselineMatchingEngine()
    # Buyer needs 25 kWh, seller offers 10 kWh
    buy = _entry(OrderSide.BUY, remaining_kwh=Decimal("25"), max_price_inr_per_kwh=Decimal("9"))
    sell = _entry(OrderSide.SELL, remaining_kwh=Decimal("10"), min_price_inr_per_kwh=Decimal("5"))

    req = _request(buys=(buy,), sells=(sell,))
    res = engine.match(req)

    assert res.trade_count == 1
    assert res.matched_kwh == Decimal("10")
    # Buyer still has 15 kWh unmatched
    assert res.unmatched_buy_order_ids == (buy.order_id,)
    assert len(res.unmatched_sell_order_ids) == 0


def test_partial_fill_seller_larger() -> None:
    engine = BaselineMatchingEngine()
    # Buyer needs 10 kWh, seller offers 30 kWh
    buy = _entry(OrderSide.BUY, remaining_kwh=Decimal("10"), max_price_inr_per_kwh=Decimal("9"))
    sell = _entry(OrderSide.SELL, remaining_kwh=Decimal("30"), min_price_inr_per_kwh=Decimal("5"))

    req = _request(buys=(buy,), sells=(sell,))
    res = engine.match(req)

    assert res.trade_count == 1
    assert res.matched_kwh == Decimal("10")
    # Seller still has 20 kWh unmatched
    assert len(res.unmatched_buy_order_ids) == 0
    assert res.unmatched_sell_order_ids == (sell.order_id,)


def test_multiple_sellers_cleared_by_price_merit_order() -> None:
    engine = BaselineMatchingEngine()
    # Buyer needs 20 kWh at up to 10 INR/kWh
    buy = _entry(OrderSide.BUY, remaining_kwh=Decimal("20"), max_price_inr_per_kwh=Decimal("10"))

    # Three sellers: cheap (4 INR/kWh), medium (6 INR/kWh), expensive (12 INR/kWh)
    sell_cheap = _entry(
        OrderSide.SELL, remaining_kwh=Decimal("10"), min_price_inr_per_kwh=Decimal("4")
    )
    sell_medium = _entry(
        OrderSide.SELL, remaining_kwh=Decimal("15"), min_price_inr_per_kwh=Decimal("6")
    )
    sell_expensive = _entry(
        OrderSide.SELL, remaining_kwh=Decimal("10"), min_price_inr_per_kwh=Decimal("12")
    )

    # Supply them in arbitrary order in the book
    req = _request(buys=(buy,), sells=(sell_expensive, sell_medium, sell_cheap))
    res = engine.match(req)

    # Expected:
    # 1. 10 kWh matched with sell_cheap @ midpoint(10, 4) = 7.0000
    # 2. Remaining 10 kWh matched with sell_medium @ midpoint(10, 6) = 8.0000
    # 3. sell_expensive not matched
    assert res.trade_count == 2
    assert res.matched_kwh == Decimal("20")

    trade1, trade2 = res.trades
    assert trade1.sell_order_id == sell_cheap.order_id
    assert trade1.quantity_kwh == Decimal("10")
    assert trade1.clearing_price_inr_per_kwh == Decimal("7.0000")

    assert trade2.sell_order_id == sell_medium.order_id
    assert trade2.quantity_kwh == Decimal("10")
    assert trade2.clearing_price_inr_per_kwh == Decimal("8.0000")

    assert len(res.unmatched_buy_order_ids) == 0
    assert res.unmatched_sell_order_ids == (sell_expensive.order_id, sell_medium.order_id) or (
        sell_medium.order_id in res.unmatched_sell_order_ids
        and sell_expensive.order_id in res.unmatched_sell_order_ids
    )


def test_multiple_buyers_cleared_by_price_merit_order() -> None:
    engine = BaselineMatchingEngine()
    # Seller offers 25 kWh at min 5 INR/kWh
    sell = _entry(OrderSide.SELL, remaining_kwh=Decimal("25"), min_price_inr_per_kwh=Decimal("5"))

    # Three buyers: high (10 INR/kWh, 10 kWh), medium (8 INR/kWh, 10 kWh), low (4 INR/kWh, 10 kWh)
    buy_high = _entry(
        OrderSide.BUY, remaining_kwh=Decimal("10"), max_price_inr_per_kwh=Decimal("10")
    )
    buy_medium = _entry(
        OrderSide.BUY, remaining_kwh=Decimal("10"), max_price_inr_per_kwh=Decimal("8")
    )
    buy_low = _entry(OrderSide.BUY, remaining_kwh=Decimal("10"), max_price_inr_per_kwh=Decimal("4"))

    req = _request(buys=(buy_low, buy_medium, buy_high), sells=(sell,))
    res = engine.match(req)

    # Expected: buy_high gets 10 kWh, buy_medium gets 10 kWh, buy_low gets 0 kWh (price < 5)
    assert res.trade_count == 2
    assert res.matched_kwh == Decimal("20")

    trade1, trade2 = res.trades
    assert trade1.buy_order_id == buy_high.order_id
    assert trade1.quantity_kwh == Decimal("10")

    assert trade2.buy_order_id == buy_medium.order_id
    assert trade2.quantity_kwh == Decimal("10")

    assert buy_low.order_id in res.unmatched_buy_order_ids
    assert sell.order_id in res.unmatched_sell_order_ids  # 5 kWh remaining


def test_deterministic_tie_breaking() -> None:
    engine = BaselineMatchingEngine()

    # Two sellers with identical price, different created_at
    early_time = T0 - (2 * HOUR)
    late_time = T0 - HOUR

    sell_early = _entry(
        OrderSide.SELL,
        remaining_kwh=Decimal("10"),
        min_price_inr_per_kwh=Decimal("5"),
        created_at=early_time,
    )
    sell_late = _entry(
        OrderSide.SELL,
        remaining_kwh=Decimal("10"),
        min_price_inr_per_kwh=Decimal("5"),
        created_at=late_time,
    )

    buy = _entry(OrderSide.BUY, remaining_kwh=Decimal("10"), max_price_inr_per_kwh=Decimal("8"))

    # Pass in late seller first; early seller must still win due to time priority
    req1 = _request(buys=(buy,), sells=(sell_late, sell_early))
    res1 = engine.match(req1)
    assert res1.trades[0].sell_order_id == sell_early.order_id

    req2 = _request(buys=(buy,), sells=(sell_early, sell_late))
    res2 = engine.match(req2)
    assert res2.trades[0].sell_order_id == sell_early.order_id


def test_zero_remaining_quantity_skipped() -> None:
    engine = BaselineMatchingEngine()
    buy_zero = _entry(
        OrderSide.BUY, remaining_kwh=Decimal("0"), max_price_inr_per_kwh=Decimal("10")
    )
    buy_valid = _entry(
        OrderSide.BUY, remaining_kwh=Decimal("10"), max_price_inr_per_kwh=Decimal("8")
    )
    sell = _entry(OrderSide.SELL, remaining_kwh=Decimal("10"), min_price_inr_per_kwh=Decimal("6"))

    req = _request(buys=(buy_zero, buy_valid), sells=(sell,))
    res = engine.match(req)

    assert res.trade_count == 1
    assert res.trades[0].buy_order_id == buy_valid.order_id
    assert res.trades[0].quantity_kwh == Decimal("10")
