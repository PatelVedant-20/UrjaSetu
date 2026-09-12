"""Unit and contract integration tests for Phase 4 Market Fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.enums import MarketType, OrderSide
from app.domain.interfaces.market import (
    MatchingEngine,
    MatchingRequest,
    MatchingResult,
    OrderBook,
    OrderBookEntry,
    ProposedTrade,
)
from tests.fixtures.market.loader import (
    build_canonical_order_book,
    get_expected_matching_result,
    get_expected_proposed_trades,
    get_market_fixtures_dir,
    load_market_fixture,
    load_market_manifest,
)
from tests.integration.phase4.conftest import StubMatchingEngine

REQUIRED_SCENARIOS = [
    "one_seller_one_buyer",
    "multiple_sellers",
    "multiple_buyers",
    "partial_fill",
    "insufficient_supply",
    "insufficient_demand",
    "buyer_max_below_seller_min",
    "compatible_time_windows",
    "incompatible_time_windows",
    "cancelled_order",
    "deterministic_tie",
]


class TestMarketManifestAndSchemas:
    """Validate manifest and raw JSON schemas for all 11 market scenarios."""

    def test_manifest_contains_all_11_scenarios(self) -> None:
        manifest = load_market_manifest()
        scenarios = manifest.get("scenarios", {})
        for req in REQUIRED_SCENARIOS:
            assert req in scenarios, f"Manifest missing required scenario: {req}"

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_scenario_json_structure(self, scenario_name: str) -> None:
        data = load_market_fixture(scenario_name)

        assert "scenario_id" in data
        assert "title" in data
        assert "market_session" in data
        assert "orders" in data
        assert "expected_clearing" in data

        session = data["market_session"]
        assert "id" in session
        assert "market_date" in session
        assert session.get("market_type") == "day_ahead"
        assert session.get("status") in ("open", "closed", "cleared")

        for order in data["orders"]:
            assert "id" in order
            assert "user_id" in order
            assert "site_id" in order
            assert order["side"] in ("buy", "sell")
            assert Decimal(str(order["energy_kwh"])) > Decimal("0")
            assert "delivery_start" in order
            assert "delivery_end" in order
            assert order["delivery_end"] > order["delivery_start"]

            if order["side"] == "buy":
                assert order.get("max_price_inr_per_kwh") is not None
            else:
                assert order.get("min_price_inr_per_kwh") is not None

    def test_referential_integrity_against_synthetic_seed(self) -> None:
        fixtures_dir = get_market_fixtures_dir()
        seed_dir = fixtures_dir.parent

        with open(seed_dir / "users.json", encoding="utf-8") as f:
            users_data = json.load(f)
        valid_user_ids = {u["id"] for u in users_data["users"]}

        with open(seed_dir / "sites.json", encoding="utf-8") as f:
            sites_data = json.load(f)
        valid_site_ids = {s["id"] for s in sites_data["sites"]}

        for sc_name in REQUIRED_SCENARIOS:
            data = load_market_fixture(sc_name)
            for order in data["orders"]:
                assert (
                    order["user_id"] in valid_user_ids
                ), f"User {order['user_id']} in {sc_name} not in users.json"
                assert (
                    order["site_id"] in valid_site_ids
                ), f"Site {order['site_id']} in {sc_name} not in sites.json"


class TestCanonicalContractLoading:
    """Validate loading fixtures directly into canonical domain dataclasses."""

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_build_canonical_order_book(self, scenario_name: str) -> None:
        book = build_canonical_order_book(scenario_name)

        assert isinstance(book, OrderBook)
        assert isinstance(book.market_session_id, UUID)
        assert book.market_type is MarketType.DAY_AHEAD

        for entry in (*book.buys, *book.sells):
            assert isinstance(entry, OrderBookEntry)
            assert isinstance(entry.order_id, UUID)
            assert isinstance(entry.user_id, UUID)
            assert isinstance(entry.site_id, UUID)
            assert isinstance(entry.remaining_kwh, Decimal)
            assert entry.remaining_kwh > Decimal("0")
            assert entry.delivery_end > entry.delivery_start

            if entry.side is OrderSide.BUY:
                assert entry.max_price_inr_per_kwh is not None
                assert entry.limit_price == entry.max_price_inr_per_kwh
            else:
                assert entry.min_price_inr_per_kwh is not None
                assert entry.limit_price == entry.min_price_inr_per_kwh

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_extract_expected_trades(self, scenario_name: str) -> None:
        trades = get_expected_proposed_trades(scenario_name)
        for trade in trades:
            assert isinstance(trade, ProposedTrade)
            assert isinstance(trade.buy_order_id, UUID)
            assert isinstance(trade.sell_order_id, UUID)
            assert trade.buy_order_id != trade.sell_order_id
            assert trade.quantity_kwh > Decimal("0")
            assert trade.clearing_price_inr_per_kwh >= Decimal("0")
            assert trade.delivery_end > trade.delivery_start


class TestDeterministicMatchingExecution:
    """Run canonical StubMatchingEngine against all 11 scenarios and verify exact outputs."""

    @pytest.fixture
    def engine(self) -> MatchingEngine:
        return StubMatchingEngine(name="stub", engine_version="1.0.0")

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_scenario_clears_with_exact_expected_result(
        self,
        engine: MatchingEngine,
        scenario_name: str,
    ) -> None:
        book = build_canonical_order_book(scenario_name)
        cleared_at = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        request = MatchingRequest(order_book=book, cleared_at=cleared_at)

        result = engine.match(request)
        expected = get_expected_matching_result(scenario_name)

        assert isinstance(result, MatchingResult)
        assert result.trade_count == expected.trade_count
        assert result.matched_kwh == expected.matched_kwh

        # Verify trades match
        assert len(result.trades) == len(expected.trades)
        for actual_t, expected_t in zip(result.trades, expected.trades, strict=True):
            assert actual_t.buy_order_id == expected_t.buy_order_id
            assert actual_t.sell_order_id == expected_t.sell_order_id
            assert actual_t.quantity_kwh == expected_t.quantity_kwh
            assert actual_t.clearing_price_inr_per_kwh == expected_t.clearing_price_inr_per_kwh
            assert actual_t.delivery_start == expected_t.delivery_start
            assert actual_t.delivery_end == expected_t.delivery_end

        # Verify unmatched order IDs
        assert set(result.unmatched_buy_order_ids) == set(expected.unmatched_buy_order_ids)
        assert set(result.unmatched_sell_order_ids) == set(expected.unmatched_sell_order_ids)

    def test_determinism_multiple_runs(self, engine: MatchingEngine) -> None:
        """Running matching multiple times on identical input yields identical trades."""
        book = build_canonical_order_book("multiple_sellers")
        request = MatchingRequest(
            order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC)
        )

        res1 = engine.match(request)
        res2 = engine.match(request)

        assert res1.trades == res2.trades
        assert res1.unmatched_sell_order_ids == res2.unmatched_sell_order_ids


class TestSpecificScenarioSemantics:
    """Deep verification of each specific market edge case."""

    def test_01_one_seller_one_buyer(self) -> None:
        book = build_canonical_order_book("one_seller_one_buyer")
        assert len(book.buys) == 1
        assert len(book.sells) == 1
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 1
        assert result.trades[0].quantity_kwh == Decimal("10.0000")
        assert result.trades[0].clearing_price_inr_per_kwh == Decimal("6.5000")

    def test_02_multiple_sellers_merit_order(self) -> None:
        book = build_canonical_order_book("multiple_sellers")
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 2
        # First trade must be at the lower price seller (5.00 min -> 6.75 clearing)
        assert result.trades[0].clearing_price_inr_per_kwh == Decimal("6.7500")
        assert result.trades[1].clearing_price_inr_per_kwh == Decimal("7.2500")

    def test_03_multiple_buyers_merit_order(self) -> None:
        book = build_canonical_order_book("multiple_buyers")
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 2
        # First trade must be at the higher bid buyer (8.00 max -> 6.50 clearing)
        assert result.trades[0].clearing_price_inr_per_kwh == Decimal("6.5000")
        assert result.trades[1].clearing_price_inr_per_kwh == Decimal("6.0000")

    def test_04_partial_fill_remainder(self) -> None:
        book = build_canonical_order_book("partial_fill")
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 1
        assert result.matched_kwh == Decimal("10.0000")
        assert len(result.unmatched_buy_order_ids) == 1

    def test_07_no_price_cross_yields_zero_trades(self) -> None:
        book = build_canonical_order_book("buyer_max_below_seller_min")
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 0
        assert result.matched_kwh == Decimal("0")
        assert len(result.unmatched_buy_order_ids) == 1
        assert len(result.unmatched_sell_order_ids) == 1

    def test_08_compatible_time_windows_intersection(self) -> None:
        book = build_canonical_order_book("compatible_time_windows")
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 1
        trade = result.trades[0]
        # Intersects at [11:00, 12:00]
        assert trade.delivery_start == datetime(2026, 6, 2, 11, 0, tzinfo=UTC)
        assert trade.delivery_end == datetime(2026, 6, 2, 12, 0, tzinfo=UTC)

    def test_09_incompatible_time_windows_zero_trades(self) -> None:
        book = build_canonical_order_book("incompatible_time_windows")
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 0

    def test_10_cancelled_order_excluded_from_book(self) -> None:
        data = load_market_fixture("cancelled_order")
        # Raw JSON has 3 orders, one of which is cancelled
        assert len(data["orders"]) == 3
        # Canonical order book must only contain the 2 active orders
        book = build_canonical_order_book("cancelled_order")
        assert len(book.sells) == 1
        assert len(book.buys) == 1
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 1

    def test_11_deterministic_tie_breaking(self) -> None:
        book = build_canonical_order_book("deterministic_tie")
        # 2 sellers at identical price (5.50), but Seller A created at 08:00 and Seller B at 08:05
        result = StubMatchingEngine().match(
            MatchingRequest(order_book=book, cleared_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC))
        )
        assert result.trade_count == 1
        # Seller A (earlier created_at) must have matched
        seller_a_id = UUID("81000000-0011-0000-0000-000000000001")
        assert result.trades[0].sell_order_id == seller_a_id
