"""Fixtures for Phase-4 Market API and Integration Tests.

Consumes canonical models and interfaces from:
  - app.db.models.market (MarketSession, Order, Trade)
  - app.domain.enums (MarketSessionStatus, MarketType, OrderSide, OrderStatus)
  - app.domain.interfaces.market (MatchingEngine, OrderBook, OrderBookEntry)
  - tests.integration.phase4.conftest (StubMatchingEngine)
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import market
from app.core.errors import NotFoundError
from app.db.models.market import MarketSession, Order, Trade
from app.domain.enums import (
    MarketSessionStatus,
    MarketType,
    OrderSide,
    OrderStatus,
)
from app.main import create_app
from tests.integration.phase4.conftest import StubMatchingEngine

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
MARKET_DATE = date(2026, 6, 2)
DELIVERY_START = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
DELIVERY_END = DELIVERY_START + timedelta(hours=1)


@pytest.fixture
def sample_market_session_id() -> uuid.UUID:
    return uuid.UUID("30000000-0000-0000-0000-000000000001")


@pytest.fixture
def sample_prosumer_user_id() -> uuid.UUID:
    return uuid.UUID("10000000-0000-0000-0000-000000000001")


@pytest.fixture
def sample_consumer_user_id() -> uuid.UUID:
    return uuid.UUID("10000000-0000-0000-0000-000000000002")


@pytest.fixture
def sample_prosumer_site_id() -> uuid.UUID:
    return uuid.UUID("40000000-0000-0000-0000-000000000001")


@pytest.fixture
def sample_consumer_site_id() -> uuid.UUID:
    return uuid.UUID("40000000-0000-0000-0000-000000000002")


@pytest.fixture
def market_client(sample_market_session_id: uuid.UUID) -> Iterator[TestClient]:
    """FastAPI TestClient for market endpoints with isolated mock service state."""
    app = create_app()
    # Ensure market router is mounted under /api/v1
    app.include_router(market.router, prefix="/api/v1")

    sessions: dict[uuid.UUID, MarketSession] = {
        sample_market_session_id: MarketSession(
            id=sample_market_session_id,
            market_date=MARKET_DATE,
            market_type=MarketType.DAY_AHEAD,
            status=MarketSessionStatus.OPEN,
            opened_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
    }
    orders: dict[uuid.UUID, Order] = {}
    trades: dict[uuid.UUID, Trade] = {}

    def mock_open_session(
        session: Any,
        *,
        market_date: date,
        market_type: MarketType = MarketType.DAY_AHEAD,
        **kwargs: Any,
    ) -> MarketSession:
        new_id = uuid.uuid4()
        s = MarketSession(
            id=new_id,
            market_date=market_date,
            market_type=market_type,
            status=MarketSessionStatus.OPEN,
            opened_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )
        sessions[new_id] = s
        return s

    def mock_get_session(session: Any, market_session_id: uuid.UUID) -> MarketSession:
        if market_session_id in sessions:
            return sessions[market_session_id]
        raise NotFoundError(
            "Market session not found.",
            code="MARKET_SESSION_NOT_FOUND",
            details={"id": str(market_session_id)},
        )

    def mock_close_session(
        session: Any, market_session_id: uuid.UUID, **kwargs: Any
    ) -> MarketSession:
        s = mock_get_session(session, market_session_id)
        s.status = MarketSessionStatus.CLOSED
        s.closed_at = NOW
        return s

    def mock_place_order(session: Any, **kwargs: Any) -> Order:
        order_id = uuid.uuid4()
        order = Order(
            id=order_id,
            market_session_id=kwargs["market_session_id"],
            user_id=kwargs["user_id"],
            site_id=kwargs["site_id"],
            node_id=kwargs.get("node_id"),
            side=kwargs["side"],
            energy_kwh=kwargs["energy_kwh"],
            min_price_inr_per_kwh=kwargs.get("min_price_inr_per_kwh"),
            max_price_inr_per_kwh=kwargs.get("max_price_inr_per_kwh"),
            delivery_start=kwargs["delivery_start"],
            delivery_end=kwargs["delivery_end"],
            forecast_basis_id=kwargs.get("forecast_basis_id"),
            reliability_score_snapshot=kwargs.get("reliability_score_snapshot"),
            status=OrderStatus.OPEN,
            matched_kwh=Decimal("0"),
            created_at=NOW,
            updated_at=NOW,
        )
        orders[order_id] = order
        return order

    def mock_get_order(session: Any, order_id: uuid.UUID) -> Order:
        if order_id in orders:
            return orders[order_id]
        raise NotFoundError(
            "Order not found.",
            code="ORDER_NOT_FOUND",
            details={"id": str(order_id)},
        )

    def mock_cancel_order(session: Any, order_id: uuid.UUID) -> Order:
        order = mock_get_order(session, order_id)
        order.status = OrderStatus.CANCELLED
        return order

    def mock_clear_session(
        session: Any, market_session_id: uuid.UUID, **kwargs: Any
    ) -> list[Trade]:
        mock_get_session(session, market_session_id)
        return []

    def mock_get_trade(session: Any, trade_id: uuid.UUID) -> Trade:
        if trade_id in trades:
            return trades[trade_id]
        raise NotFoundError(
            "Trade not found.",
            code="TRADE_NOT_FOUND",
            details={"id": str(trade_id)},
        )

    with (
        patch("app.services.market_service.open_session", side_effect=mock_open_session),
        patch("app.services.market_service.get_session", side_effect=mock_get_session),
        patch("app.services.market_service.close_session", side_effect=mock_close_session),
        patch("app.services.market_service.place_order", side_effect=mock_place_order),
        patch("app.services.market_service.get_order", side_effect=mock_get_order),
        patch("app.services.market_service.cancel_order", side_effect=mock_cancel_order),
        patch("app.services.market_service.clear_session", side_effect=mock_clear_session),
        patch("app.services.market_service.get_trade", side_effect=mock_get_trade),
        TestClient(app) as client,
    ):
        yield client


@pytest.fixture
def test_stub_engine() -> StubMatchingEngine:
    return StubMatchingEngine()


@pytest.fixture
def make_session_payload() -> dict[str, Any]:
    return {
        "market_date": MARKET_DATE.isoformat(),
        "market_type": MarketType.DAY_AHEAD.value,
    }


@pytest.fixture
def make_buy_order_payload(
    sample_market_session_id: uuid.UUID,
    sample_consumer_user_id: uuid.UUID,
    sample_consumer_site_id: uuid.UUID,
) -> dict[str, Any]:
    return {
        "market_session_id": str(sample_market_session_id),
        "user_id": str(sample_consumer_user_id),
        "site_id": str(sample_consumer_site_id),
        "side": OrderSide.BUY.value,
        "energy_kwh": 10.0,
        "max_price_inr_per_kwh": 8.0,
        "delivery_start": DELIVERY_START.isoformat(),
        "delivery_end": DELIVERY_END.isoformat(),
    }


@pytest.fixture
def make_sell_order_payload(
    sample_market_session_id: uuid.UUID,
    sample_prosumer_user_id: uuid.UUID,
    sample_prosumer_site_id: uuid.UUID,
) -> dict[str, Any]:
    return {
        "market_session_id": str(sample_market_session_id),
        "user_id": str(sample_prosumer_user_id),
        "site_id": str(sample_prosumer_site_id),
        "side": OrderSide.SELL.value,
        "energy_kwh": 10.0,
        "min_price_inr_per_kwh": 6.0,
        "delivery_start": DELIVERY_START.isoformat(),
        "delivery_end": DELIVERY_END.isoformat(),
    }
