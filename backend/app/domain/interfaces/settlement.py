"""The settlement and reconciliation contract.

The stable boundary between UrjaSetu and whatever computes a settlement:

    trade + effective price + committed energy + actual energy
        -> SettlementRequest -> SettlementCalculator -> SettlementResult

docs/01_FINAL_ARCHITECTURE.md gives the `settlement` module one job:
"Actual-versus-committed reconciliation, adjustments, buyer/seller accounting",
and names the reliability path it implements:

    commitment -> actual -> deviation -> tolerance -> balancing adjustment

This module declares the shape of that. It holds no arithmetic, no tolerance
and no fee — those live in `app/domain/policies/settlement.py` so the rules can
change without touching anything that consumes a settlement.

**Four quantities, never conflated.** The single most common way a settlement
layer goes wrong is to treat these as interchangeable:

* ``committed_quantity_kwh`` — what the two parties **agreed**, from the Phase 4
  trade.
* ``forecast_quantity_kwh`` — what was **predicted**, from the Phase 3 run the
  sell order was placed against. Traceability and explanation only; nobody is
  paid on a forecast.
* ``ActualEnergy.quantity_kwh`` — what the meter **actually recorded**. May be
  `None`, which means *not measured* and never *zero*.
* ``settled_quantity_kwh`` — what is **finally settled**, after the tolerance
  policy has been applied to the first and third.

**Units, stated in every name** (docs/00_PROJECT_BIBLE.md section 6): energy is
`_kwh`, price is `_inr_per_kwh`, money is `_inr`. Every one is a `Decimal`; no
float touches an energy or a money value.

**What this phase does not do.** It never re-runs matching, grid validation,
forecasting or pricing. It never recomputes a price: the effective price is an
input, resolved through `EffectivePriceResolver`, which is what keeps exactly
one pricing engine in the codebase. It never moves real money — there is no
payment gateway, and `buyer_debit_inr` / `seller_credit_inr` are a simulated
ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.enums import ReconciliationStatus, SettlementStatus

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# What actually happened
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActualEnergy:
    """Measured delivery over a window, with the provenance to judge it.

    A plain number would not be enough. `quantity_kwh` is `None` when the
    telemetry system has nothing usable for the window, and settlement must be
    able to tell that apart from a measured zero: the first means "we do not
    know", the second means "nothing was delivered", and only the second is a
    shortfall anyone can be charged for.

    `reading_count` is how many usable readings the total came from, so a
    settlement can record that a window was thinly covered without having to
    re-query telemetry to find out.
    """

    window_start: datetime
    window_end: datetime
    quantity_kwh: Decimal | None = None
    reading_count: int = 0
    # How the figure was obtained, for the audit trail — e.g. which telemetry
    # query and quality filter produced it.
    source: str = "telemetry"

    @property
    def is_measured(self) -> bool:
        """Whether a usable figure exists at all."""
        return self.quantity_kwh is not None

    @property
    def window(self) -> timedelta:
        return self.window_end - self.window_start


# ---------------------------------------------------------------------------
# The effective price, as a dependency rather than a calculation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EffectivePrice:
    """The price a trade settles at, and where it came from.

    Phase 6 produces two prices and they are not interchangeable:
    `trades.clearing_price_inr_per_kwh` is the Phase 4 market clearing price,
    and `price_components.final_price` is the effective price after the
    dynamic-pricing components. **Settlement uses the effective one**, which
    the Phase 6 handoff identified as the decision this phase had to make
    explicitly rather than by accident.

    `source_id` points at the `price_components` row, so a settled amount can
    always be traced back to the breakdown that justified its price.
    """

    price_inr_per_kwh: Decimal
    source_id: UUID | None = None
    formula_version: str | None = None


@runtime_checkable
class EffectivePriceResolver(Protocol):
    """Where settlement obtains the Phase 6 effective price.

    A boundary, not an implementation. Settlement never recomputes a price and
    never contains a copy of the pricing formula; it asks. That keeps exactly
    one pricing engine in the repository, and it means the Phase 6 API work
    landing later changes nothing here.
    """

    def effective_price_for(self, trade_id: UUID) -> EffectivePrice:
        """The effective price for a trade.

        Raises rather than guessing when no price has been calculated. A
        settlement that invented a price would be unauditable, and falling back
        to the Phase 4 clearing price would silently discard every dynamic
        component.
        """
        ...


@runtime_checkable
class ActualEnergyResolver(Protocol):
    """Where settlement obtains measured delivery.

    A boundary over the Phase 2 telemetry system. Settlement does not read
    meter rows, does not re-implement quality classification, and does not
    decide what counts as a usable reading — telemetry already owns all three.
    """

    def actual_energy_for(self, *, site_id: UUID, start: datetime, end: datetime) -> ActualEnergy:
        """Energy measured at a site over `[start, end]`.

        Returns an unmeasured `ActualEnergy` rather than zero when the window
        holds no usable readings.
        """
        ...


# ---------------------------------------------------------------------------
# Reconciliation — what happened versus what was agreed
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    """The comparison, kept separate from the money.

    Mirrors docs/04_DATA_MODEL.md entity 19 (`meter_reconciliations`) field for
    field, so what is computed and what is stored cannot drift apart.

    Reconciliation explains the difference between commitment and reality. It
    decides how much energy is settleable; it does not decide what anything
    costs. Keeping the two apart is what lets a tolerance rule change without
    touching the accounting, and vice versa.
    """

    committed_quantity_kwh: Decimal
    actual_quantity_kwh: Decimal | None
    # Signed: negative is a shortfall against the commitment, positive an
    # over-delivery. `None` when nothing was measured.
    deviation_kwh: Decimal | None
    deviation_pct: Decimal | None
    within_tolerance: bool
    # The part of the commitment that was not delivered and must be covered by
    # the grid instead. Zero unless the shortfall breached the tolerance.
    balancing_kwh: Decimal
    # What may actually be paid for. `None` while nothing has been measured.
    settled_quantity_kwh: Decimal | None
    status: ReconciliationStatus
    reason: str
    policy_version: str

    @property
    def is_shortfall(self) -> bool:
        return self.deviation_kwh is not None and self.deviation_kwh < ZERO

    @property
    def is_complete(self) -> bool:
        return self.status.is_complete


# ---------------------------------------------------------------------------
# Settlement — the money
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SettlementRequest:
    """Everything a settlement depends on, stated explicitly.

    Assembled by `app.services.settlement_service` from the canonical owners
    and handed to the calculator as plain values. No ORM object crosses this
    boundary: a calculator that received one could lazy-load a relationship
    mid-calculation and make the same stored inputs produce a different amount.
    """

    trade_id: UUID
    buyer_user_id: UUID
    seller_user_id: UUID

    # WHAT WAS AGREED — from the Phase 4 trade.
    committed_quantity_kwh: Decimal
    # WHAT IT COSTS — from Phase 6, never recomputed here.
    effective_price: EffectivePrice

    delivery_start: datetime
    delivery_end: datetime

    # WHAT ACTUALLY HAPPENED — from Phase 2.
    actual: ActualEnergy

    # WHAT WAS FORECAST — from Phase 3. Explanation and traceability only:
    # nobody is paid on a prediction.
    forecast_quantity_kwh: Decimal | None = None

    # ---- traceability, carried through to the stored rows ----
    forecast_basis_id: UUID | None = None
    grid_validation_id: UUID | None = None

    @property
    def delivery_window(self) -> timedelta:
        return self.delivery_end - self.delivery_start


@dataclass(frozen=True, slots=True)
class SettlementResult:
    """An auditable settlement.

    The money fields are exactly docs/04_DATA_MODEL.md entity 20
    (`settlements`), in INR, so what is computed and what is stored cannot
    drift apart. The reconciliation that produced the settled quantity travels
    with it rather than being recomputed by whoever reads the result.

    **The ledger must balance.** What the buyer is debited equals what the
    seller is credited plus everything the platform retained:

        buyer_debit_inr = seller_credit_inr + platform_fee_inr
                                            + balancing_charge_inr

    Checked at the service boundary and enforced again by a database
    constraint, because a settlement whose sides disagree is not a settlement.
    """

    trade_id: UUID
    buyer_user_id: UUID
    seller_user_id: UUID

    settled_quantity_kwh: Decimal
    effective_price_inr_per_kwh: Decimal

    gross_amount_inr: Decimal
    platform_fee_inr: Decimal
    balancing_charge_inr: Decimal
    buyer_debit_inr: Decimal
    seller_credit_inr: Decimal

    status: SettlementStatus
    policy_version: str
    reconciliation: ReconciliationOutcome

    # ---- traceability ----
    price_components_id: UUID | None = None
    forecast_basis_id: UUID | None = None
    grid_validation_id: UUID | None = None

    lines: Sequence[SettlementLine] = field(default_factory=tuple)

    @property
    def platform_retained_inr(self) -> Decimal:
        return self.platform_fee_inr + self.balancing_charge_inr

    @property
    def ledger_balances(self) -> bool:
        return self.buyer_debit_inr == self.seller_credit_inr + self.platform_retained_inr


@dataclass(frozen=True, slots=True)
class SettlementLine:
    """One itemised entry, so an amount can be explained rather than asserted.

    Not persisted: docs/04_DATA_MODEL.md entity 20 stores totals, and adding a
    table the data model does not define would be inventing schema. These exist
    so an API response, a dashboard or the Phase 8 audit trail can say *why*
    each total is what it is.
    """

    label: str
    quantity_kwh: Decimal | None
    price_inr_per_kwh: Decimal | None
    # Signed from the platform's point of view is ambiguous, so it is not:
    # this is the magnitude, and `label` says who it moves between.
    amount_inr: Decimal
    reason: str


@runtime_checkable
class SettlementCalculator(Protocol):
    """What a settlement implementation must provide.

    Deliberately tiny — the same shape as `GridEngine`, `ForecastProvider` and
    `PricingEngine`, for the same reason: a calculator that needed a session or
    a clock could not be replayed, and a settlement that cannot be reproduced
    cannot be audited.

    `policy_version` is stored on every settlement. Change it whenever the same
    request could produce different amounts, so a past settlement stays
    explainable after the rules move on.
    """

    @property
    def name(self) -> str:
        """Stable identifier of the implementation."""
        ...

    @property
    def policy_version(self) -> str:
        """Version of the reconciliation and accounting rules."""
        ...

    def settle(self, request: SettlementRequest) -> SettlementResult:
        """Reconcile, then account.

        Must be deterministic: identical requests produce identical amounts,
        with no clock, no randomness and no I/O.

        Must never treat unmeasured telemetry as zero delivery. A request whose
        `actual` is unmeasured yields a `PENDING` settlement, not a shortfall
        charged to the seller.
        """
        ...
