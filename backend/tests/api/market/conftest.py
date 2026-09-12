"""Fixtures for Phase-4 Market API and Integration Tests.

Consumes canonical models and interfaces from:
  - app.db.models.market (MarketSession, Order, Trade)
  - app.domain.enums (MarketSessionStatus, MarketType, OrderSide, OrderStatus, TradeStatus)
  - app.domain.interfaces.market (MatchingEngine, MatchingRequest, MatchingResult, OrderBook, OrderBookEntry, ProposedTrade)
  - tests.integration.phase4.conftest (StubMatchingEngine, FailingMatchingEngine, MisbehavingMatchingEngine)
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import (
    MarketSessionStatus,
    MarketType,
    OrderSide,
    OrderStatus,
    TradeStatus,
)
from app.main import create_app
from tests.integration.phase4.conftest import (
    StubMatchingEngine,
    FailingMatchingEngine,
    MisbehavingMatchingEngine,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
MARKET_DATE = date(2026, 6, 2)
DELIVERY_START = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
DELIVERY_END = DELIVERY_START + timedelta(hours=1)


@pytest.fixture
def market_client() -> Iterator[TestClient]:
    """FastAPI TestClient for market endpoints."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def test_stub_engine() -> StubMatchingEngine:
    return StubMatchingEngine()


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
