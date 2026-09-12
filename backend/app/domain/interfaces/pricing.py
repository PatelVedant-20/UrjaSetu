"""The dynamic pricing contract.

The stable boundary between UrjaSetu and whatever computes an effective price:

    base clearing price -> PricingRequest -> PricingEngine -> PricingResult

docs/01_FINAL_ARCHITECTURE.md gives the `pricing` module exactly one job:
"Base price + time + congestion + imbalance/risk + local-renewable component".
This module declares the shape of that calculation; it contains none of the
arithmetic, which lives in `app/domain/policies/dynamic_pricing.py` so the
formula can be replaced without touching anything that consumes a price.

**Separation of responsibilities** (docs/00_PROJECT_BIBLE.md section 4). The
market decides *who* trades with *whom* and *how much*. Grid validation decides
*whether* the trade is physically safe. Pricing decides *what it costs*. None
of the three may absorb another: a matching engine that knew about congestion
would make the same trade price differently depending on which algorithm ran,
and a grid adapter that knew about money would make a physical result depend on
a tariff.

An engine is **pure**. It receives plain values and returns plain values. It
never opens a session, reads a row, or knows that PostgreSQL, FastAPI, a market
or a ledger exist — which is what makes a stored price reproducible from its
stored inputs (docs/00_PROJECT_BIBLE.md: traceability).

Units, unchanged (docs/00_PROJECT_BIBLE.md section 6): every price and every
component is **INR/kWh**, as `Decimal`, quantised by
`app.domain.policies.clearing_price.quantize_price`. No float ever touches a
price.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.enums import (
    GridValidationDecision,
    GridValidationStatus,
    PriceComponentKind,
)
from app.domain.interfaces.grid import GridMetrics, GridViolation

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PriceComponent:
    """One itemised part of a price, with the reason it applied.

    docs/05_API_SPEC.md requires the breakdown to explain *why* the price
    changed, so a component carries prose as well as a number. The reason is
    written by the policy that produced the component, which is the only place
    that knows the threshold it crossed.
    """

    kind: PriceComponentKind
    # INR/kWh. Signed: positive adds to the price, negative subtracts from it.
    amount_inr_per_kwh: Decimal
    reason: str


@dataclass(frozen=True, slots=True)
class PricingRequest:
    """Everything a price may depend on, stated explicitly.

    Assembled by `app.services.pricing_service` from the canonical sources —
    the Phase 4 trade, the Phase 5 validation run, the Phase 3 forecast — and
    handed to the engine as plain values. Nothing here is an ORM object: an
    engine that received one could lazy-load a relationship mid-calculation and
    make the same stored inputs produce a different price.
    """

    # The Phase 4 clearing price, which Phase 6 adjusts and never recomputes.
    base_price_inr_per_kwh: Decimal
    quantity_kwh: Decimal
    delivery_start: datetime
    delivery_end: datetime

    # ---- grid state (Phase 5) ----
    #
    # Defaults to UNKNOWN, and deliberately not to None-means-fine. A trade
    # that has never been validated and a trade whose solver crashed are the
    # same epistemic state: nobody has established that this is safe. Making
    # UNKNOWN the default means forgetting to pass the grid state produces the
    # cautious price, not the cheap one.
    grid_status: GridValidationStatus = GridValidationStatus.UNKNOWN
    grid_metrics: GridMetrics | None = None
    caused_violations: Sequence[GridViolation] = field(default_factory=tuple)

    # ---- forecast risk (Phase 3) ----
    #
    # The confidence of the forecast this trade was sold against, in [0, 1].
    # None means the provider reported none — a naive baseline has no
    # meaningful uncertainty — which is itself treated as an unknown, not as
    # certainty.
    forecast_confidence: Decimal | None = None

    # ---- locality (Phase 1 twin) ----
    local_renewable: bool = False

    # ---- traceability, carried through to the stored breakdown ----
    trade_id: UUID | None = None
    grid_validation_id: UUID | None = None
    forecast_basis_id: UUID | None = None

    @property
    def interval(self) -> timedelta:
        return self.delivery_end - self.delivery_start


@dataclass(frozen=True, slots=True)
class PricingResult:
    """An explainable price.

    The five numeric fields are exactly the columns of
    docs/04_DATA_MODEL.md entity 18, in the same units, so what is returned and
    what is stored cannot drift apart.

    **The components always sum to the final price.** Every adjustment is
    quantised before it is added, the sum is taken over quantised values, and
    nothing is clamped afterwards — a post-hoc floor or ceiling would make the
    stored breakdown stop adding up, which is the one thing an explainable
    price may not do. Bounds are applied inside each component instead, where
    the reason for the bound can be recorded.
    """

    formula_version: str
    engine: str

    base_market_price: Decimal
    time_component: Decimal
    congestion_component: Decimal
    imbalance_component: Decimal
    local_renewable_component: Decimal
    final_price: Decimal

    components: Sequence[PriceComponent] = field(default_factory=tuple)

    # What pricing suggests happens to this trade. A recommendation only:
    # Phase 6 never mutates a trade, approves one, or overrides Phase 5.
    recommended_decision: GridValidationDecision = GridValidationDecision.ACCEPT
    grid_status: GridValidationStatus = GridValidationStatus.UNKNOWN

    @property
    def adjustment(self) -> Decimal:
        """How far the effective price moved from the base, signed."""
        return self.final_price - self.base_market_price

    @property
    def components_sum(self) -> Decimal:
        """The five parts added up.

        Equal to `final_price` for any result a conforming engine produced;
        the service checks it at the boundary before storing anything.
        """
        return (
            self.base_market_price
            + self.time_component
            + self.congestion_component
            + self.imbalance_component
            + self.local_renewable_component
        )

    @property
    def is_repriced(self) -> bool:
        return self.recommended_decision is GridValidationDecision.REPRICE


@runtime_checkable
class PricingEngine(Protocol):
    """What a pricing implementation must provide.

    Deliberately tiny: one identity pair and one pure method — the same shape
    as `GridEngine` and `ForecastProvider`, because the same rule applies. An
    engine that needed a session or a clock could not be replayed.

    `formula_version` is stored on every breakdown
    (`price_components.formula_version`). Change it whenever the same request
    could produce a different price, so a past price stays explainable after
    the formula moves on.
    """

    @property
    def name(self) -> str:
        """Stable identifier of the implementation."""
        ...

    @property
    def formula_version(self) -> str:
        """Version of the formula and its coefficients."""
        ...

    def quote(self, request: PricingRequest) -> PricingResult:
        """Price one trade or prospective trade.

        Must be deterministic: identical requests produce identical prices,
        with no clock, no randomness and no I/O. A price that could not be
        reproduced could not be audited or settled against.

        Must never treat `GridValidationStatus.UNKNOWN` as `SAFE`. An
        unavailable or failed grid validation cannot receive the pricing
        treatment of a network that was checked and found unconstrained.
        """
        ...
