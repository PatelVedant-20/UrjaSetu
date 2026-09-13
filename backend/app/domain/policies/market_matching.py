"""Baseline Market Matching Engine for UrjaSetu.

Implements the canonical MatchingEngine protocol defined in
app.domain.interfaces.market.

ALGORITHM & ORDER PRIORITY:
---------------------------
Implements a deterministic Continuous Double Auction / Merit-Order Clearing:
1. Priority Queue Ordering:
   - BUY orders (demand) are sorted by:
       1. Limit price DESCENDING (highest willingness to pay first)
       2. created_at ASCENDING (earliest order placed first)
       3. order_id ASCENDING (deterministic total tie-break)
   - SELL orders (supply) are sorted by:
       1. Limit price ASCENDING (lowest asking price first)
       2. created_at ASCENDING (earliest order placed first)
       3. order_id ASCENDING (deterministic total tie-break)

2. Matching & Clearing:
   - Evaluates buy orders in merit order against available sell orders.
   - Requires price compatibility: sell.min_price <= buy.max_price (via prices_cross).
   - Requires delivery time overlap: max(buy_start, sell_start) < min(buy_end, sell_end).
   - Trade quantity is min(buyer_remaining, seller_remaining) (never over-fills).
   - Clearing price is computed via midpoint_clearing_price.

3. Purity & Determinism:
   - 100% pure function of MatchingRequest.
   - Zero database/I/O, zero clock access, zero side-effects.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.domain.interfaces.market import (
    ZERO,
    MatchingRequest,
    MatchingResult,
    ProposedTrade,
)
from app.domain.policies.clearing_price import midpoint_clearing_price, prices_cross


class BaselineMatchingEngine:
    """Deterministic Merit-Order Double Auction Matching Engine.

    Satisfies the app.domain.interfaces.market.MatchingEngine protocol.
    """

    def __init__(
        self,
        name: str = "baseline_double_auction",
        engine_version: str = "0.1.0",
    ) -> None:
        self._name = name
        self._engine_version = engine_version

    @property
    def name(self) -> str:
        """Stable identifier for the matching engine."""
        return self._name

    @property
    def engine_version(self) -> str:
        """Version of the matching algorithm."""
        return self._engine_version

    def match(self, request: MatchingRequest) -> MatchingResult:
        """Pair buyers with sellers deterministically from the order book."""
        book = request.order_book

        # If either side of the book is empty, no trades can be formed
        if book.is_empty:
            return MatchingResult(
                engine=self._name,
                engine_version=self._engine_version,
                trades=(),
                unmatched_buy_order_ids=tuple(b.order_id for b in book.buys),
                unmatched_sell_order_ids=tuple(s.order_id for s in book.sells),
            )

        # 1. Filter and sort buyers (Merit order: price desc, created_at asc, order_id asc)
        valid_buys = [
            b for b in book.buys if b.remaining_kwh > ZERO and b.max_price_inr_per_kwh is not None
        ]
        sorted_buys = sorted(
            valid_buys,
            key=lambda b: (-b.max_price_inr_per_kwh, b.created_at, b.order_id),  # type: ignore[operator]
        )

        # 2. Filter and sort sellers (Merit order: price asc, created_at asc, order_id asc)
        valid_sells = [
            s for s in book.sells if s.remaining_kwh > ZERO and s.min_price_inr_per_kwh is not None
        ]
        sorted_sells = sorted(
            valid_sells,
            key=lambda s: (s.min_price_inr_per_kwh, s.created_at, s.order_id),
        )

        # Track remaining quantities during matching
        rem_buys: dict[UUID, Decimal] = {b.order_id: b.remaining_kwh for b in sorted_buys}
        rem_sells: dict[UUID, Decimal] = {s.order_id: s.remaining_kwh for s in sorted_sells}

        trades: list[ProposedTrade] = []

        # 3. Double Auction matching loop
        for buy in sorted_buys:
            if rem_buys[buy.order_id] <= ZERO:
                continue

            for sell in sorted_sells:
                if sell.user_id == buy.user_id:
                    continue
                if rem_sells[sell.order_id] <= ZERO:
                    continue

                # Check price compatibility
                if not prices_cross(
                    buy_max_inr_per_kwh=buy.max_price_inr_per_kwh,
                    sell_min_inr_per_kwh=sell.min_price_inr_per_kwh,
                ):
                    continue

                # Check delivery window overlap
                overlap_start = max(buy.delivery_start, sell.delivery_start)
                overlap_end = min(buy.delivery_end, sell.delivery_end)
                if overlap_end <= overlap_start:
                    continue

                # Determine trade quantity
                trade_qty = min(rem_buys[buy.order_id], rem_sells[sell.order_id])
                if trade_qty <= ZERO:
                    continue

                assert buy.max_price_inr_per_kwh is not None
                assert sell.min_price_inr_per_kwh is not None
                clearing_price = midpoint_clearing_price(
                    buy_max_inr_per_kwh=buy.max_price_inr_per_kwh,
                    sell_min_inr_per_kwh=sell.min_price_inr_per_kwh,
                )

                trade = ProposedTrade(
                    buy_order_id=buy.order_id,
                    sell_order_id=sell.order_id,
                    quantity_kwh=trade_qty,
                    clearing_price_inr_per_kwh=clearing_price,
                    delivery_start=overlap_start,
                    delivery_end=overlap_end,
                )
                trades.append(trade)

                rem_buys[buy.order_id] -= trade_qty
                rem_sells[sell.order_id] -= trade_qty

                if rem_buys[buy.order_id] <= ZERO:
                    break

        # 4. Determine unmatched orders
        unmatched_buys = [
            b.order_id for b in book.buys if rem_buys.get(b.order_id, b.remaining_kwh) > ZERO
        ]
        unmatched_sells = [
            s.order_id for s in book.sells if rem_sells.get(s.order_id, s.remaining_kwh) > ZERO
        ]

        return MatchingResult(
            engine=self._name,
            engine_version=self._engine_version,
            trades=tuple(trades),
            unmatched_buy_order_ids=tuple(unmatched_buys),
            unmatched_sell_order_ids=tuple(unmatched_sells),
        )


# Canonical alias
ContinuousDoubleAuctionMatchingEngine = BaselineMatchingEngine
