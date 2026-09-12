"""Loader utility for Phase 4 Market Fixtures.

Consumes canonical domain contracts and models:
    OrderBook, OrderBookEntry, ProposedTrade, MatchingResult
    MarketType, OrderSide, OrderStatus
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from app.domain.enums import MarketType, OrderSide, OrderStatus
from app.domain.interfaces.market import (
    MatchingResult,
    OrderBook,
    OrderBookEntry,
    ProposedTrade,
)


def get_market_fixtures_dir() -> Path:
    """Resolve the absolute path to data/synthetic/market."""
    base = Path(__file__).resolve()
    # backend/tests/fixtures/market/loader.py -> repo root
    repo_root = base.parents[4]
    fixtures_dir = repo_root / "data" / "synthetic" / "market"
    if not fixtures_dir.exists():
        raise FileNotFoundError(f"Market fixtures directory not found: {fixtures_dir}")
    return fixtures_dir


def load_market_manifest() -> dict[str, Any]:
    """Load the master market manifest."""
    manifest_path = get_market_fixtures_dir() / "market_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Market manifest not found: {manifest_path}")
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def list_available_market_scenarios() -> list[str]:
    """Return list of available scenario identifiers."""
    manifest = load_market_manifest()
    return list(manifest.get("scenarios", {}).keys())


def _resolve_fixture_path(scenario_name: str) -> Path:
    fixtures_dir = get_market_fixtures_dir()
    if scenario_name.endswith(".json"):
        path = fixtures_dir / scenario_name
        if path.exists():
            return path

    # Try exact match or file mapping from manifest
    manifest = load_market_manifest()
    scenarios = manifest.get("scenarios", {})
    if scenario_name in scenarios:
        filename = scenarios[scenario_name]["file"]
        return fixtures_dir / filename

    # Try appending .json or matching filename without prefix
    candidate = fixtures_dir / f"{scenario_name}.json"
    if candidate.exists():
        return candidate

    for entry in scenarios.values():
        if entry.get("file", "").endswith(f"{scenario_name}.json"):
            return fixtures_dir / entry["file"]

    raise FileNotFoundError(
        f"Market scenario fixture '{scenario_name}' not found. Available: {list(scenarios.keys())}"
    )


def load_market_fixture(scenario_name: str) -> dict[str, Any]:
    """Load raw JSON fixture data for a scenario."""
    fixture_path = _resolve_fixture_path(scenario_name)
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


def _parse_utc_datetime(iso_str: str) -> datetime:
    """Parse ISO datetime and ensure UTC timezone."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.astimezone(UTC)


def build_canonical_order_book(scenario_name: str) -> OrderBook:
    """Project active orders in scenario into the canonical OrderBook contract."""
    data = load_market_fixture(scenario_name)
    session_data = data["market_session"]

    session_id = UUID(session_data["id"])
    market_date = date.fromisoformat(session_data["market_date"])
    market_type = MarketType(session_data.get("market_type", "day_ahead"))

    buys: list[OrderBookEntry] = []
    sells: list[OrderBookEntry] = []

    for o in data.get("orders", []):
        status_val = o.get("status", "open")
        order_status = OrderStatus(status_val)

        # Only active orders enter the order book (mirroring market_service.build_order_book)
        if not order_status.is_active:
            continue

        side = OrderSide(o["side"])
        energy_kwh = Decimal(str(o["energy_kwh"]))
        matched_kwh = Decimal(str(o.get("matched_kwh", "0")))
        remaining_kwh = energy_kwh - matched_kwh

        entry = OrderBookEntry(
            order_id=UUID(o["id"]),
            side=side,
            user_id=UUID(o["user_id"]),
            site_id=UUID(o["site_id"]),
            node_id=UUID(o["node_id"]) if o.get("node_id") else None,
            remaining_kwh=remaining_kwh,
            delivery_start=_parse_utc_datetime(o["delivery_start"]),
            delivery_end=_parse_utc_datetime(o["delivery_end"]),
            created_at=_parse_utc_datetime(o["created_at"]),
            max_price_inr_per_kwh=Decimal(str(o["max_price_inr_per_kwh"]))
            if o.get("max_price_inr_per_kwh") is not None
            else None,
            min_price_inr_per_kwh=Decimal(str(o["min_price_inr_per_kwh"]))
            if o.get("min_price_inr_per_kwh") is not None
            else None,
            reliability_score_snapshot=Decimal(str(o["reliability_score_snapshot"]))
            if o.get("reliability_score_snapshot") is not None
            else None,
        )

        if side is OrderSide.BUY:
            buys.append(entry)
        else:
            sells.append(entry)

    return OrderBook(
        market_session_id=session_id,
        market_date=market_date,
        market_type=market_type,
        buys=tuple(buys),
        sells=tuple(sells),
    )


def get_expected_proposed_trades(scenario_name: str) -> list[ProposedTrade]:
    """Extract expected candidate trades from fixture into canonical ProposedTrade objects."""
    data = load_market_fixture(scenario_name)
    clearing = data.get("expected_clearing", {})
    expected_list = clearing.get("trades", [])

    trades: list[ProposedTrade] = []
    for t in expected_list:
        trade = ProposedTrade(
            buy_order_id=UUID(t["buy_order_id"]),
            sell_order_id=UUID(t["sell_order_id"]),
            quantity_kwh=Decimal(str(t["quantity_kwh"])),
            clearing_price_inr_per_kwh=Decimal(str(t["clearing_price_inr_per_kwh"])),
            delivery_start=_parse_utc_datetime(t["delivery_start"]),
            delivery_end=_parse_utc_datetime(t["delivery_end"]),
        )
        trades.append(trade)

    return trades


def get_expected_matching_result(
    scenario_name: str,
    engine_name: str = "stub",
    engine_version: str = "1.0.0",
) -> MatchingResult:
    """Build expected canonical MatchingResult dataclass for scenario."""
    data = load_market_fixture(scenario_name)
    clearing = data.get("expected_clearing", {})

    trades = get_expected_proposed_trades(scenario_name)
    unmatched_buys = [UUID(uid) for uid in clearing.get("unmatched_buy_order_ids", [])]
    unmatched_sells = [UUID(uid) for uid in clearing.get("unmatched_sell_order_ids", [])]

    return MatchingResult(
        engine=engine_name,
        engine_version=engine_version,
        trades=tuple(trades),
        unmatched_buy_order_ids=tuple(unmatched_buys),
        unmatched_sell_order_ids=tuple(unmatched_sells),
    )
