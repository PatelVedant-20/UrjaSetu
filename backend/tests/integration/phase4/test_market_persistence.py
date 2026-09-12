"""Phase 4: market persistence.

Proves `market_sessions`, `orders` and `trades` store the entities of
docs/04_DATA_MODEL.md with the constraints the data model requires, and that
integrity is enforced by the database rather than only in Python.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MarketSession, Order, Site, Trade, User
from app.domain.enums import (
    MarketSessionStatus,
    MarketType,
    OrderSide,
    OrderStatus,
    TradeStatus,
)

MARKET_DATE = date(2026, 6, 2)
D0 = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
D1 = D0 + timedelta(hours=1)

PHASE_4_TABLES = {"market_sessions", "orders", "trades"}


def _session_row(**overrides: object) -> MarketSession:
    defaults: dict[str, object] = {
        "market_date": MARKET_DATE,
        "market_type": MarketType.DAY_AHEAD,
        "status": MarketSessionStatus.OPEN,
        "opened_at": datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    }
    return MarketSession(**{**defaults, **overrides})  # type: ignore[arg-type]


def _order_row(
    session_id: uuid.UUID, user_id: uuid.UUID, site_id: uuid.UUID, **kw: object
) -> Order:
    defaults: dict[str, object] = {
        "market_session_id": session_id,
        "user_id": user_id,
        "site_id": site_id,
        "side": OrderSide.BUY,
        "energy_kwh": Decimal("10.0"),
        "max_price_inr_per_kwh": Decimal("8.0"),
        "delivery_start": D0,
        "delivery_end": D1,
        "status": OrderStatus.OPEN,
    }
    return Order(**{**defaults, **kw})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_market_tables_exist(engine) -> None:  # type: ignore[no-untyped-def]
    assert PHASE_4_TABLES.issubset(set(inspect(engine).get_table_names()))


def test_orders_columns_match_the_data_model(engine) -> None:  # type: ignore[no-untyped-def]
    """docs/04_DATA_MODEL.md entity 14, plus the shared conventions."""
    columns = {c["name"] for c in inspect(engine).get_columns("orders")}

    assert columns == {
        "id",
        "market_session_id",
        "user_id",
        "site_id",
        "node_id",
        "side",
        "energy_kwh",
        "min_price_inr_per_kwh",
        "max_price_inr_per_kwh",
        "delivery_start",
        "delivery_end",
        "forecast_basis_id",
        "reliability_score_snapshot",
        "status",
        "matched_kwh",
        "created_at",
        "updated_at",
    }


# ---------------------------------------------------------------------------
# Market sessions
# ---------------------------------------------------------------------------


def test_create_market_session(db_session: Session) -> None:
    market_session = _session_row()
    db_session.add(market_session)
    db_session.flush()

    assert isinstance(market_session.id, uuid.UUID)
    assert market_session.market_type is MarketType.DAY_AHEAD
    assert market_session.status is MarketSessionStatus.OPEN
    assert market_session.opened_at is not None
    assert market_session.opened_at.tzinfo is not None


def test_one_session_per_date_and_type(db_session: Session) -> None:
    """Two open books for one day could sell the same energy twice."""
    db_session.add(_session_row())
    db_session.flush()

    db_session.add(_session_row())
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_session_timestamps_must_be_ordered(db_session: Session) -> None:
    db_session.add(
        _session_row(
            opened_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            closed_at=datetime(2026, 6, 1, 11, 0, tzinfo=UTC),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def test_create_buy_and_sell_orders(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    site = make_site(owner_user_id=user.id)

    buy = _order_row(ms.id, user.id, site.id)
    sell = _order_row(
        ms.id,
        user.id,
        site.id,
        side=OrderSide.SELL,
        max_price_inr_per_kwh=None,
        min_price_inr_per_kwh=Decimal("6.0"),
    )
    db_session.add_all([buy, sell])
    db_session.flush()

    assert buy.side is OrderSide.BUY
    assert buy.remaining_kwh == Decimal("10.0000")
    assert sell.min_price_inr_per_kwh == Decimal("6.0000")
    assert sell.status is OrderStatus.OPEN


def test_buy_requires_a_max_price(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """docs/04_DATA_MODEL.md entity 14: "buy requires max price"."""
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(
        _order_row(ms.id, user.id, make_site(owner_user_id=user.id).id, max_price_inr_per_kwh=None)
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_sell_requires_a_min_price(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """docs/04_DATA_MODEL.md entity 14: "sell requires min price"."""
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(
        _order_row(
            ms.id,
            user.id,
            make_site(owner_user_id=user.id).id,
            side=OrderSide.SELL,
            max_price_inr_per_kwh=None,
            min_price_inr_per_kwh=None,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("energy_kwh", Decimal("0")),
        ("energy_kwh", Decimal("-1")),
        ("max_price_inr_per_kwh", Decimal("-0.0001")),
    ],
)
def test_invalid_order_values_are_rejected(
    db_session: Session,
    make_user: Callable[..., User],
    make_site: Callable[..., Site],
    field: str,
    value: Decimal,
) -> None:
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(
        _order_row(ms.id, user.id, make_site(owner_user_id=user.id).id, **{field: value})
    )

    with pytest.raises((IntegrityError, DataError)):
        db_session.flush()


def test_delivery_window_must_be_non_empty(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(
        _order_row(
            ms.id,
            user.id,
            make_site(owner_user_id=user.id).id,
            delivery_start=D1,
            delivery_end=D0,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_matched_energy_cannot_exceed_the_order(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """Over-filling would sell energy the participant never offered."""
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(
        _order_row(
            ms.id,
            user.id,
            make_site(owner_user_id=user.id).id,
            energy_kwh=Decimal("5"),
            matched_kwh=Decimal("6"),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_reliability_snapshot_must_be_a_ratio(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(
        _order_row(
            ms.id,
            user.id,
            make_site(owner_user_id=user.id).id,
            reliability_score_snapshot=Decimal("1.5"),
        )
    )

    with pytest.raises((IntegrityError, DataError)):
        db_session.flush()


def test_order_requires_an_existing_session(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    user = make_user()
    db_session.add(_order_row(uuid.uuid4(), user.id, make_site(owner_user_id=user.id).id))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_user_with_orders_is_blocked(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """An order is a commitment; deleting the user must not erase it."""
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(_order_row(ms.id, user.id, make_site(owner_user_id=user.id).id))
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})


def test_deleting_a_session_cascades_to_its_orders(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    user = make_user()
    db_session.add(_order_row(ms.id, user.id, make_site(owner_user_id=user.id).id))
    db_session.flush()

    db_session.execute(text("DELETE FROM market_sessions WHERE id = :sid"), {"sid": ms.id})
    db_session.flush()

    remaining = db_session.execute(
        text("SELECT count(*) FROM orders WHERE market_session_id = :sid"), {"sid": ms.id}
    ).scalar_one()
    assert remaining == 0


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


def _pair(db_session: Session, user: User, site: Site) -> tuple[Order, Order]:
    ms = _session_row()
    db_session.add(ms)
    db_session.flush()
    buy = _order_row(ms.id, user.id, site.id)
    sell = _order_row(
        ms.id,
        user.id,
        site.id,
        side=OrderSide.SELL,
        max_price_inr_per_kwh=None,
        min_price_inr_per_kwh=Decimal("6.0"),
    )
    db_session.add_all([buy, sell])
    db_session.flush()
    return buy, sell


def test_create_proposed_trade(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    user = make_user()
    buy, sell = _pair(db_session, user, make_site(owner_user_id=user.id))

    trade = Trade(
        buy_order_id=buy.id,
        sell_order_id=sell.id,
        quantity_kwh=Decimal("5.0"),
        clearing_price_inr_per_kwh=Decimal("7.0"),
        delivery_start=D0,
        delivery_end=D1,
        matching_engine="stub",
        matching_engine_version="1.0.0",
    )
    db_session.add(trade)
    db_session.flush()

    # Phase 4 only ever proposes; approval is a later phase.
    assert trade.status is TradeStatus.PROPOSED
    assert trade.committed_at is None
    assert trade.grid_validation_id is None


def test_trade_cannot_pair_an_order_with_itself(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    user = make_user()
    buy, _ = _pair(db_session, user, make_site(owner_user_id=user.id))

    db_session.add(
        Trade(
            buy_order_id=buy.id,
            sell_order_id=buy.id,
            quantity_kwh=Decimal("1"),
            clearing_price_inr_per_kwh=Decimal("7"),
            delivery_start=D0,
            delivery_end=D1,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_pairing_for_one_window_is_rejected(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """Re-running clearing must not duplicate a candidate."""
    user = make_user()
    buy, sell = _pair(db_session, user, make_site(owner_user_id=user.id))
    for _ in range(2):
        db_session.add(
            Trade(
                buy_order_id=buy.id,
                sell_order_id=sell.id,
                quantity_kwh=Decimal("1"),
                clearing_price_inr_per_kwh=Decimal("7"),
                delivery_start=D0,
                delivery_end=D1,
            )
        )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_trade_status_vocabulary_is_locked_to_proposed(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """Phase 4 can only ever propose.

    Approval and commitment states arrive with the phases that define them, so
    the database rejects any other value outright rather than letting code
    branch on an outcome no phase can produce.
    """
    assert [status.value for status in TradeStatus] == ["proposed"]

    user = make_user()
    buy, sell = _pair(db_session, user, make_site(owner_user_id=user.id))
    trade = Trade(
        buy_order_id=buy.id,
        sell_order_id=sell.id,
        quantity_kwh=Decimal("1"),
        clearing_price_inr_per_kwh=Decimal("7"),
        delivery_start=D0,
        delivery_end=D1,
    )
    db_session.add(trade)
    db_session.flush()

    assert trade.status is TradeStatus.PROPOSED
    # `committed_at` exists because docs/04_DATA_MODEL.md entity 15 lists it,
    # and stays NULL until a settlement phase can set it.
    assert trade.committed_at is None

    with pytest.raises((IntegrityError, DataError)):
        db_session.execute(
            text("UPDATE trades SET status = 'committed' WHERE id = :tid"), {"tid": trade.id}
        )


def test_enums_persist_as_lowercase_values(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    user = make_user()
    buy, sell = _pair(db_session, user, make_site(owner_user_id=user.id))

    row = db_session.execute(
        text("SELECT side::text, status::text FROM orders WHERE id = :oid"), {"oid": sell.id}
    ).one()

    assert row == ("sell", "open")
