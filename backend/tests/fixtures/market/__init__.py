"""Market fixtures package for UrjaSetu Phase 4.

Exports loader functions that consume canonical market contracts.
"""

from tests.fixtures.market.loader import (
    build_canonical_order_book,
    get_expected_matching_result,
    get_expected_proposed_trades,
    get_market_fixtures_dir,
    list_available_market_scenarios,
    load_market_fixture,
    load_market_manifest,
)

__all__ = [
    "build_canonical_order_book",
    "get_expected_matching_result",
    "get_expected_proposed_trades",
    "get_market_fixtures_dir",
    "list_available_market_scenarios",
    "load_market_fixture",
    "load_market_manifest",
]
