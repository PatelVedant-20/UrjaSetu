"""Phase 4: the matching contract itself.

Proves the boundary is structural — an implementation only has to match the
shape, with no import of, or inheritance from, UrjaSetu base classes. That is
what lets a future optimiser replace the baseline engine without touching the
market service, the schema or the API.

Pure: no database, no clock.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.domain.enums import MarketType, OrderSide
from app.domain.interfaces.market import (
    MatchingEngine,
    MatchingRequest,
    MatchingResult,
    OrderBook,
    OrderBookEntry,
    ProposedTrade,
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


def _book(**overrides: object) -> OrderBook:
    defaults: dict[str, object] = {
        "market_session_id": uuid4(),
        "market_date": date(2026, 6, 2),
        "market_type": MarketType.DAY_AHEAD,
        "buys": (_entry(OrderSide.BUY),),
        "sells": (_entry(OrderSide.SELL),),
    }
    return OrderBook(**{**defaults, **overrides})  # type: ignore[arg-type]


class ThirdPartyEngine:
    """An engine written with no knowledge of UrjaSetu's internals."""

    name = "third-party"
    engine_version = "0.1"

    def match(self, request: MatchingRequest) -> MatchingResult:
        buy = request.order_book.buys[0]
        sell = request.order_book.sells[0]
        return MatchingResult(
            engine=self.name,
            engine_version=self.engine_version,
            trades=(
                ProposedTrade(
                    buy_order_id=buy.order_id,
                    sell_order_id=sell.order_id,
                    quantity_kwh=Decimal("5"),
                    clearing_price_inr_per_kwh=Decimal("7"),
                    delivery_start=T0,
                    delivery_end=T0 + HOUR,
                ),
            ),
        )


def test_an_unrelated_class_satisfies_the_engine_type() -> None:
    engine: MatchingEngine = ThirdPartyEngine()

    assert isinstance(engine, MatchingEngine)
    assert engine.name == "third-party"


def test_engine_returns_the_contract_types() -> None:
    result = ThirdPartyEngine().match(MatchingRequest(order_book=_book(), cleared_at=T0))

    assert isinstance(result, MatchingResult)
    assert all(isinstance(t, ProposedTrade) for t in result.trades)
    assert result.matched_kwh == Decimal("5")
    assert result.trade_count == 1


def test_limit_price_is_side_specific() -> None:
    """A buy carries its ceiling, a sell its floor (docs/04_DATA_MODEL.md)."""
    buy = _entry(OrderSide.BUY)
    sell = _entry(OrderSide.SELL)

    assert buy.limit_price == Decimal("8")
    assert sell.limit_price == Decimal("6")
    assert buy.min_price_inr_per_kwh is None
    assert sell.max_price_inr_per_kwh is None


def test_delivery_overlap_is_half_open() -> None:
    """Orders that merely touch at a boundary do not overlap."""
    first = _entry(OrderSide.BUY, delivery_start=T0, delivery_end=T0 + HOUR)
    touching = _entry(OrderSide.SELL, delivery_start=T0 + HOUR, delivery_end=T0 + 2 * HOUR)
    overlapping = _entry(OrderSide.SELL, delivery_start=T0 + HOUR / 2, delivery_end=T0 + 2 * HOUR)

    assert first.overlaps(touching) is False
    assert first.overlaps(overlapping) is True
    # Symmetric.
    assert overlapping.overlaps(first) is True


def test_order_book_totals() -> None:
    book = _book(
        buys=(_entry(OrderSide.BUY, remaining_kwh=Decimal("4")), _entry(OrderSide.BUY)),
        sells=(_entry(OrderSide.SELL, remaining_kwh=Decimal("3")),),
    )

    assert book.total_demand_kwh == Decimal("14")
    assert book.total_supply_kwh == Decimal("3")
    assert book.is_empty is False


def test_a_one_sided_book_is_empty() -> None:
    """Nothing can clear without both sides."""
    assert _book(buys=()).is_empty is True
    assert _book(sells=()).is_empty is True


def test_request_exposes_the_session_it_clears() -> None:
    book = _book()
    request = MatchingRequest(order_book=book, cleared_at=T0)

    assert request.market_session_id == book.market_session_id
    # The clearing instant is supplied, never read from a clock by the engine.
    assert request.cleared_at == T0


def test_contract_objects_are_immutable() -> None:
    """An order book entry and a proposed trade are facts about a moment."""
    for obj, attr, value in (
        (_entry(OrderSide.BUY), "remaining_kwh", Decimal("99")),
        (_book(), "market_session_id", uuid4()),
        (
            ProposedTrade(
                buy_order_id=uuid4(),
                sell_order_id=uuid4(),
                quantity_kwh=Decimal("1"),
                clearing_price_inr_per_kwh=Decimal("1"),
                delivery_start=T0,
                delivery_end=T0 + HOUR,
            ),
            "quantity_kwh",
            Decimal("99"),
        ),
    ):
        try:
            setattr(obj, attr, value)
        except Exception as exc:
            assert exc.__class__.__name__ == "FrozenInstanceError"
        else:  # pragma: no cover - a mutable contract object is a defect
            raise AssertionError(f"{type(obj).__name__}.{attr} should be immutable")


def test_result_reports_unmatched_orders_explicitly() -> None:
    """An engine may decline to match; saying so beats leaving it inferred."""
    unmatched = uuid4()
    result = MatchingResult(engine="e", engine_version="1", unmatched_buy_order_ids=(unmatched,))

    assert result.trades == ()
    assert result.matched_kwh == Decimal("0")
    assert result.unmatched_buy_order_ids == (unmatched,)


def test_engine_never_needs_persistence_or_transport() -> None:
    """The contract module must not import persistence, transport or adapters.

    Asserted on the imports rather than on the source text, so the module is
    free to *discuss* PostgreSQL and FastAPI in its docstring while depending
    on neither.
    """
    import ast

    import app.domain.interfaces.market as contract

    assert contract.__file__ is not None
    tree = ast.parse(Path(contract.__file__).read_text())

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = ("sqlalchemy", "fastapi", "app.db", "app.repositories", "app.adapters", "app.api")
    offending = [
        name for name in imported if any(name == f or name.startswith(f + ".") for f in forbidden)
    ]
    assert not offending, f"the matching contract must not import {offending}"


# ---------------------------------------------------------------------------
# Locked vocabularies (Phase 4 contract finalisation)
# ---------------------------------------------------------------------------


def test_market_session_status_vocabulary_is_locked() -> None:
    """Exactly three states: open, closed, cleared."""
    from app.domain.enums import MarketSessionStatus

    assert [s.value for s in MarketSessionStatus] == ["open", "closed", "cleared"]


def test_order_status_vocabulary_is_locked() -> None:
    """Fill vocabulary, not matching vocabulary."""
    from app.domain.enums import OrderStatus

    assert [s.value for s in OrderStatus] == [
        "open",
        "partially_filled",
        "filled",
        "cancelled",
        "rejected",
    ]


def test_trade_status_vocabulary_is_locked() -> None:
    """Phase 4 proposes and nothing else.

    Approval and commitment states arrive with the phases that define them, so
    that no code can branch on an outcome no phase can produce.
    """
    from app.domain.enums import TradeStatus

    assert [s.value for s in TradeStatus] == ["proposed"]


def test_only_open_and_partially_filled_orders_are_active() -> None:
    """An active order is one that still has energy to fill."""
    from app.domain.enums import OrderStatus

    active = {s for s in OrderStatus if s.is_active}

    assert active == {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}
    assert all(s.is_terminal for s in OrderStatus if s not in active)


def test_session_state_gates_are_exclusive() -> None:
    """Orders are taken while open; clearing happens only once intake closed."""
    from app.domain.enums import MarketSessionStatus

    assert [s for s in MarketSessionStatus if s.accepts_orders] == [MarketSessionStatus.OPEN]
    assert [s for s in MarketSessionStatus if s.can_clear] == [MarketSessionStatus.CLOSED]
