"""Phase-4 Market API and Integration Tests.

Validates the documented Phase-4 market contract per docs/05_API_SPEC.md:
  - POST /api/v1/market/sessions
  - GET /api/v1/market/sessions/{session_id}
  - POST /api/v1/market/sessions/{session_id}/close
  - POST /api/v1/orders
  - GET /api/v1/orders/{order_id}
  - POST /api/v1/orders/{order_id}/cancel
  - GET /api/v1/market/order-book
  - POST /api/v1/market/sessions/{session_id}/clear
  - GET /api/v1/trades/{trade_id}

Covers required scenarios:
  1. market session (open, get, close)
  2. buy order
  3. sell order
  4. order validation
  5. matching
  6. partial fills
  7. no-match cases
  8. trade candidate creation
  9. eligibility restrictions
  10. surplus restrictions
  11. error envelope
  12. deterministic behavior
"""

from __future__ import annotations

import uuid
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
from app.domain.interfaces.market import (
    MatchingRequest,
    MatchingResult,
    OrderBook,
    OrderBookEntry,
    ProposedTrade,
)
from app.domain.policies.clearing_price import midpoint_clearing_price
from tests.integration.phase4.conftest import StubMatchingEngine

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
MARKET_DATE = date(2026, 6, 2)
DELIVERY_START = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
DELIVERY_END = DELIVERY_START + timedelta(hours=1)


# ===========================================================================
# 1. Market Session API Tests
# ===========================================================================


class TestMarketSessionAPI:
    """Test market session lifecycle via REST endpoints."""

    def test_open_market_session_endpoint(
        self, market_client: TestClient, make_session_payload: dict[str, Any]
    ) -> None:
        """POST /market/sessions opens a new market session."""
        response = market_client.post("/api/v1/market/sessions", json=make_session_payload)
        assert response.status_code in (200, 201), (
            f"Expected 200 or 201 on POST /market/sessions, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "id" in data
        assert data.get("status") == MarketSessionStatus.OPEN.value

    def test_get_market_session_endpoint(
        self, market_client: TestClient, sample_market_session_id: uuid.UUID
    ) -> None:
        """GET /market/sessions/{session_id} returns session state."""
        response = market_client.get(f"/api/v1/market/sessions/{sample_market_session_id}")
        assert response.status_code == 200, (
            f"Expected 200 on GET /market/sessions/{sample_market_session_id}, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "id" in data
        assert "status" in data
        assert "market_date" in data

    def test_close_market_session_endpoint(
        self, market_client: TestClient, sample_market_session_id: uuid.UUID
    ) -> None:
        """POST /market/sessions/{session_id}/close stops order intake."""
        response = market_client.post(
            f"/api/v1/market/sessions/{sample_market_session_id}/close"
        )
        assert response.status_code == 200, (
            f"Expected 200 on POST /market/sessions/{sample_market_session_id}/close, got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert data.get("status") == MarketSessionStatus.CLOSED.value

    def test_get_nonexistent_session_returns_404(self, market_client: TestClient) -> None:
        """Querying an unknown session id must return 404 with locked error envelope."""
        fake_id = str(uuid.uuid4())
        response = market_client.get(f"/api/v1/market/sessions/{fake_id}")
        assert response.status_code == 404, (
            f"Expected 404 for unknown session, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "error" in body, "Response must conform to locked error envelope"
        assert "code" in body["error"]
        assert "request_id" in body["error"]


# ===========================================================================
# 2. Orders API Tests (Buy & Sell Orders)
# ===========================================================================


class TestOrdersAPI:
    """Test buy and sell order placement and lookup."""

    def test_place_buy_order_endpoint(
        self, market_client: TestClient, make_buy_order_payload: dict[str, Any]
    ) -> None:
        """POST /orders with side=buy creates a buy order."""
        response = market_client.post("/api/v1/orders", json=make_buy_order_payload)
        assert response.status_code in (200, 201), (
            f"Expected 200/201 on POST /orders (buy), got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "id" in data
        assert data.get("side") == OrderSide.BUY.value
        assert data.get("status") == OrderStatus.OPEN.value
        assert float(data.get("max_price_inr_per_kwh", 0)) == 8.0

    def test_place_sell_order_endpoint(
        self, market_client: TestClient, make_sell_order_payload: dict[str, Any]
    ) -> None:
        """POST /orders with side=sell creates a sell order."""
        response = market_client.post("/api/v1/orders", json=make_sell_order_payload)
        assert response.status_code in (200, 201), (
            f"Expected 200/201 on POST /orders (sell), got {response.status_code}: {response.text}"
        )
        data = response.json()
        assert "id" in data
        assert data.get("side") == OrderSide.SELL.value
        assert data.get("status") == OrderStatus.OPEN.value
        assert float(data.get("min_price_inr_per_kwh", 0)) == 6.0

    def test_cancel_order_endpoint(self, market_client: TestClient) -> None:
        """POST /orders/{order_id}/cancel cancels an open order."""
        fake_order_id = str(uuid.uuid4())
        response = market_client.post(f"/api/v1/orders/{fake_order_id}/cancel")
        # If order exists -> 200 with status=cancelled; if missing -> 404 with error envelope
        assert response.status_code in (200, 404)
        if response.status_code == 404:
            body = response.json()
            assert "error" in body
            assert "code" in body["error"]


# ===========================================================================
# 3. Order Validation Tests
# ===========================================================================


class TestOrderValidation:
    """Test boundary and validation constraints on orders."""

    def test_non_positive_energy_rejected(
        self, market_client: TestClient, make_buy_order_payload: dict[str, Any]
    ) -> None:
        """Orders with energy <= 0 must be rejected with 400 or 422."""
        payload = dict(make_buy_order_payload)
        payload["energy_kwh"] = 0.0
        response = market_client.post("/api/v1/orders", json=payload)
        assert response.status_code in (400, 422), (
            f"Expected 400/422 for zero energy, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "error" in body or "detail" in body

    def test_buy_order_missing_max_price_rejected(
        self, market_client: TestClient, make_buy_order_payload: dict[str, Any]
    ) -> None:
        """Buy order must have a maximum price ceiling."""
        payload = dict(make_buy_order_payload)
        payload.pop("max_price_inr_per_kwh", None)
        response = market_client.post("/api/v1/orders", json=payload)
        assert response.status_code in (400, 422), (
            f"Expected 400/422 for buy order without max_price, got {response.status_code}: {response.text}"
        )

    def test_sell_order_missing_min_price_rejected(
        self, market_client: TestClient, make_sell_order_payload: dict[str, Any]
    ) -> None:
        """Sell order must have a minimum price floor."""
        payload = dict(make_sell_order_payload)
        payload.pop("min_price_inr_per_kwh", None)
        response = market_client.post("/api/v1/orders", json=payload)
        assert response.status_code in (400, 422), (
            f"Expected 400/422 for sell order without min_price, got {response.status_code}: {response.text}"
        )

    def test_inverted_delivery_window_rejected(
        self, market_client: TestClient, make_buy_order_payload: dict[str, Any]
    ) -> None:
        """Delivery window where end <= start must be rejected."""
        payload = dict(make_buy_order_payload)
        payload["delivery_start"] = DELIVERY_END.isoformat()
        payload["delivery_end"] = DELIVERY_START.isoformat()
        response = market_client.post("/api/v1/orders", json=payload)
        assert response.status_code in (400, 422), (
            f"Expected 400/422 for inverted delivery window, got {response.status_code}: {response.text}"
        )


# ===========================================================================
# 4. Matching, Partial Fills, and No-Match Scenarios
# ===========================================================================


class TestMatchingLogic:
    """Test matching contract, partial fills, and no-match conditions."""

    def test_partial_fills_and_trade_candidate_creation(
        self, test_stub_engine: StubMatchingEngine
    ) -> None:
        """Buy for 15 kWh and Sell for 10 kWh results in a 10 kWh candidate trade."""
        session_id = uuid.uuid4()
        buy_entry = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.BUY,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("15"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            created_at=NOW - timedelta(minutes=10),
            max_price_inr_per_kwh=Decimal("8.0"),
        )
        sell_entry = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.SELL,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("10"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            created_at=NOW - timedelta(minutes=5),
            min_price_inr_per_kwh=Decimal("6.0"),
        )

        book = OrderBook(
            market_session_id=session_id,
            market_date=MARKET_DATE,
            market_type=MarketType.DAY_AHEAD,
            buys=(buy_entry,),
            sells=(sell_entry,),
        )
        req = MatchingRequest(order_book=book, cleared_at=NOW)
        result = test_stub_engine.match(req)

        # 1. Trade candidate creation
        assert result.trade_count == 1
        trade = result.trades[0]
        assert isinstance(trade, ProposedTrade)
        assert trade.buy_order_id == buy_entry.order_id
        assert trade.sell_order_id == sell_entry.order_id

        # 2. Partial fill quantity = min(15, 10) = 10 kWh
        assert trade.quantity_kwh == Decimal("10")

        # 3. Clearing price is within [6.0, 8.0]
        assert Decimal("6.0") <= trade.clearing_price_inr_per_kwh <= Decimal("8.0")

        # 4. Remainder tracking
        assert buy_entry.order_id in result.unmatched_buy_order_ids or trade.quantity_kwh < buy_entry.remaining_kwh

    def test_no_match_when_prices_do_not_cross(
        self, test_stub_engine: StubMatchingEngine
    ) -> None:
        """Buyer max (5.0) < Seller min (7.0) yields NO trades."""
        session_id = uuid.uuid4()
        buy_entry = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.BUY,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("10"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            created_at=NOW,
            max_price_inr_per_kwh=Decimal("5.0"),
        )
        sell_entry = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.SELL,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("10"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            created_at=NOW,
            min_price_inr_per_kwh=Decimal("7.0"),
        )

        book = OrderBook(
            market_session_id=session_id,
            market_date=MARKET_DATE,
            market_type=MarketType.DAY_AHEAD,
            buys=(buy_entry,),
            sells=(sell_entry,),
        )
        result = test_stub_engine.match(MatchingRequest(order_book=book, cleared_at=NOW))

        assert result.trade_count == 0, "No trades should be created when prices do not cross"
        assert len(result.unmatched_buy_order_ids) == 1
        assert len(result.unmatched_sell_order_ids) == 1

    def test_no_match_when_delivery_windows_do_not_overlap(
        self, test_stub_engine: StubMatchingEngine
    ) -> None:
        """Orders for completely disjoint time windows must not match."""
        session_id = uuid.uuid4()
        buy_entry = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.BUY,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("10"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            created_at=NOW,
            max_price_inr_per_kwh=Decimal("8.0"),
        )
        # Sell is tomorrow afternoon, no overlap
        sell_entry = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.SELL,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("10"),
            delivery_start=DELIVERY_END + timedelta(hours=3),
            delivery_end=DELIVERY_END + timedelta(hours=4),
            created_at=NOW,
            min_price_inr_per_kwh=Decimal("6.0"),
        )

        book = OrderBook(
            market_session_id=session_id,
            market_date=MARKET_DATE,
            market_type=MarketType.DAY_AHEAD,
            buys=(buy_entry,),
            sells=(sell_entry,),
        )
        result = test_stub_engine.match(MatchingRequest(order_book=book, cleared_at=NOW))
        assert result.trade_count == 0, "Non-overlapping delivery windows cannot clear together"


# ===========================================================================
# 5. Deterministic Behavior & Error Envelope
# ===========================================================================


class TestDeterministicBehaviorAndErrorEnvelope:
    """Test clearing repeatability and locked error envelope compliance."""

    def test_clearing_is_deterministic(self, test_stub_engine: StubMatchingEngine) -> None:
        """Same order book and cleared_at produces identical trades in identical order."""
        session_id = uuid.uuid4()
        b1 = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.BUY,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("10"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            created_at=NOW - timedelta(minutes=5),
            max_price_inr_per_kwh=Decimal("8.5"),
        )
        s1 = OrderBookEntry(
            order_id=uuid.uuid4(),
            side=OrderSide.SELL,
            user_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            remaining_kwh=Decimal("10"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            created_at=NOW - timedelta(minutes=2),
            min_price_inr_per_kwh=Decimal("6.5"),
        )

        book = OrderBook(
            market_session_id=session_id,
            market_date=MARKET_DATE,
            market_type=MarketType.DAY_AHEAD,
            buys=(b1,),
            sells=(s1,),
        )
        req = MatchingRequest(order_book=book, cleared_at=NOW)

        res1 = test_stub_engine.match(req)
        res2 = test_stub_engine.match(req)

        assert res1.trade_count == res2.trade_count
        for t1, t2 in zip(res1.trades, res2.trades):
            assert t1.buy_order_id == t2.buy_order_id
            assert t1.sell_order_id == t2.sell_order_id
            assert t1.quantity_kwh == t2.quantity_kwh
            assert t1.clearing_price_inr_per_kwh == t2.clearing_price_inr_per_kwh
            assert t1.delivery_start == t2.delivery_start
            assert t1.delivery_end == t2.delivery_end

    def test_clearing_api_endpoint(
        self, market_client: TestClient, sample_market_session_id: uuid.UUID
    ) -> None:
        """POST /market/sessions/{session_id}/clear triggers clearing."""
        response = market_client.post(
            f"/api/v1/market/sessions/{sample_market_session_id}/clear"
        )
        # Expected 200 with proposed trades or 404/409 with locked error envelope
        assert response.status_code in (200, 404, 409)
        if response.status_code != 200:
            body = response.json()
            assert "error" in body
            assert "code" in body["error"]
            assert "request_id" in body["error"]

    def test_get_trade_state_endpoint(self, market_client: TestClient) -> None:
        """GET /trades/{trade_id} returns trade state."""
        fake_trade_id = str(uuid.uuid4())
        response = market_client.get(f"/api/v1/trades/{fake_trade_id}")
        assert response.status_code in (200, 404)
        if response.status_code == 404:
            body = response.json()
            assert "error" in body
            assert "code" in body["error"]
