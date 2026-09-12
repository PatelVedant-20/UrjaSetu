"""The market matching contract.

This is the stable boundary between the marketplace and whatever algorithm
pairs buyers with sellers:

    orders -> OrderBook -> MatchingRequest -> MatchingEngine -> MatchingResult
    -> proposed trades

Nothing here knows how matching is done. A simple price-time engine, a
merit-order clearing, or a future optimiser all satisfy the same Protocol, so
the engine can be replaced without touching the market service, the schema or
the API (docs/06_OPEN_SOURCE_INTEGRATION.md: InterConnect and GSY-E are
references, not runtime dependencies).

An engine is **pure**. It receives a market state and returns a result. It
never opens a session, reads a row, calls an API, or knows that PostgreSQL,
FastAPI, a power-flow solver or a ledger exist. That is what makes clearing
reproducible from stored inputs (docs/00_PROJECT_BIBLE.md: traceability) and
deterministic (docs/10_TESTING_AND_INTEGRATION.md).

Units follow docs/00_PROJECT_BIBLE.md section 6 — energy in kWh, price in
INR/kWh, timestamps timezone-aware UTC — and are never converted here.

Phase 4 produces *candidates*. docs/05_API_SPEC.md is explicit that clearing
"does not silently bypass grid validation", so a `ProposedTrade` is an
intention, never an approved or committed one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.enums import MarketType, OrderSide

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class OrderBookEntry:
    """One order, reduced to what matching needs.

    Deliberately not the ORM model: an engine that took `app.db.models.market.
    Order` would be coupled to persistence, and could lazy-load a relationship
    mid-match. This carries identifiers, not objects.

    Exactly one price bound is meaningful per side, mirroring
    docs/04_DATA_MODEL.md entity 14: a BUY carries the most it will pay, a SELL
    the least it will accept.
    """

    order_id: UUID
    side: OrderSide
    user_id: UUID
    site_id: UUID
    # Energy still available to match — the original quantity minus whatever
    # earlier clearing already filled, so a partially matched order re-enters
    # the book at its remainder rather than its original size.
    remaining_kwh: Decimal
    delivery_start: datetime
    delivery_end: datetime
    created_at: datetime

    node_id: UUID | None = None
    # BUY: the ceiling. SELL: None.
    max_price_inr_per_kwh: Decimal | None = None
    # SELL: the floor. BUY: None.
    min_price_inr_per_kwh: Decimal | None = None
    # Seller trustworthiness at the moment the order was placed, frozen so a
    # later change cannot retroactively alter how a past clearing behaved.
    reliability_score_snapshot: Decimal | None = None

    @property
    def limit_price(self) -> Decimal | None:
        """The price bound that applies to this order's side."""
        if self.side is OrderSide.BUY:
            return self.max_price_inr_per_kwh
        return self.min_price_inr_per_kwh

    def overlaps(self, other: OrderBookEntry) -> bool:
        """Whether two orders share any delivery time.

        Half-open intervals, so orders that merely touch at a boundary do not
        count as overlapping.
        """
        return self.delivery_start < other.delivery_end and other.delivery_start < self.delivery_end


@dataclass(frozen=True, slots=True)
class OrderBook:
    """The matchable state of one market session at a moment in time."""

    market_session_id: UUID
    market_date: date
    market_type: MarketType
    buys: Sequence[OrderBookEntry] = field(default_factory=tuple)
    sells: Sequence[OrderBookEntry] = field(default_factory=tuple)

    @property
    def total_demand_kwh(self) -> Decimal:
        return sum((entry.remaining_kwh for entry in self.buys), ZERO)

    @property
    def total_supply_kwh(self) -> Decimal:
        return sum((entry.remaining_kwh for entry in self.sells), ZERO)

    @property
    def is_empty(self) -> bool:
        return not self.buys or not self.sells


@dataclass(frozen=True, slots=True)
class MatchingRequest:
    """Everything an engine needs to clear a session.

    Self-contained on purpose: a request can be logged and replayed to explain
    why a particular set of trades was proposed.
    """

    order_book: OrderBook
    # Captured once by the service and passed in, so an engine never reads a
    # clock and the same request always clears the same way.
    cleared_at: datetime

    @property
    def market_session_id(self) -> UUID:
        return self.order_book.market_session_id


@dataclass(frozen=True, slots=True)
class ProposedTrade:
    """One candidate pairing produced by an engine.

    Not a commitment. It becomes binding only after grid validation and
    approval in later phases.
    """

    buy_order_id: UUID
    sell_order_id: UUID
    quantity_kwh: Decimal
    clearing_price_inr_per_kwh: Decimal
    delivery_start: datetime
    delivery_end: datetime


@dataclass(frozen=True, slots=True)
class MatchingResult:
    """What an engine returns.

    `engine` and `engine_version` identify what produced this clearing, so a
    stored trade can always be attributed to a specific implementation at a
    specific version.

    Unmatched order ids are reported rather than inferred: an engine may
    legitimately decline to match an order, and saying so explicitly is more
    useful than leaving the service to work it out.
    """

    engine: str
    engine_version: str
    trades: Sequence[ProposedTrade] = field(default_factory=tuple)
    unmatched_buy_order_ids: Sequence[UUID] = field(default_factory=tuple)
    unmatched_sell_order_ids: Sequence[UUID] = field(default_factory=tuple)

    @property
    def matched_kwh(self) -> Decimal:
        return sum((trade.quantity_kwh for trade in self.trades), ZERO)

    @property
    def trade_count(self) -> int:
        return len(self.trades)


@runtime_checkable
class MatchingEngine(Protocol):
    """What a matching implementation must provide.

    Implementations live in `app/domain/policies/market_matching.py` and are
    owned by the agent assigned that module. This declaration is the contract
    they implement, not an implementation.

    Deliberately tiny: one identity pair and one pure method. Anything an
    engine needs beyond that — tie-breaking rules, optimisation budget — is its
    own constructor's business, invisible to the market service.
    """

    @property
    def name(self) -> str:
        """Stable identifier, persisted with the clearing."""
        ...

    @property
    def engine_version(self) -> str:
        """Version of the algorithm.

        Change it whenever the same order book could clear differently, so a
        past clearing stays explainable.
        """
        ...

    def match(self, request: MatchingRequest) -> MatchingResult:
        """Pair buyers with sellers.

        Must be deterministic: the same request yields the same result, with
        trades in a stable order. Any tie-breaking must be total — by price,
        then by `created_at`, then by `order_id` — so two runs cannot disagree.

        Must not over-fill: the quantities assigned to any one order across all
        returned trades must not exceed that order's `remaining_kwh`. The
        service verifies this rather than trusting it.

        Raise on failure rather than returning a partial result; the service
        records the clearing as failed and surfaces a typed error.
        """
        ...
