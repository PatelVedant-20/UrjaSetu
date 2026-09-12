"""Reconciliation and settlement rules.

Two responsibilities, kept apart because they answer different questions and
change for different reasons:

* **Reconciliation** — what happened compared with what was agreed, and how
  much of the commitment is therefore settleable. Energy only.
* **Accounting** — what the settleable energy is worth, and who owes whom.
  Money only.

docs/01_FINAL_ARCHITECTURE.md names the path this implements:

    commitment -> actual -> deviation -> tolerance -> balancing adjustment

Pure and deterministic: plain values in, plain values out, no I/O and no clock.

--------------------------------------------------------------------------
THE TOLERANCE AND THE FEE ARE PROVISIONAL
--------------------------------------------------------------------------
No project document specifies a deviation tolerance, a penalty, a balancing
price or a platform fee. docs/04_DATA_MODEL.md entity 19 requires a
`within_tolerance` flag and a `balancing_kwh` figure, and entity 20 requires a
`platform_fee_inr` and a `balancing_charge_inr` column — the *columns* are
canonical, the *numbers* are not specified anywhere.

Every unspecified number therefore lives in `SettlementPolicy`, marked
PROVISIONAL, with the reasoning for its default written beside it. Two of the
three defaults are chosen to invent as little as possible: the platform fee
defaults to **zero** rather than to a made-up rate, and balancing is charged at
the trade's own effective price rather than at an invented penalty price. Only
the tolerance band has no such neutral choice, and it is the decision most in
need of a ruling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.domain.enums import ReconciliationStatus, SettlementStatus
from app.domain.interfaces.settlement import (
    ActualEnergy,
    ReconciliationOutcome,
    SettlementLine,
    SettlementRequest,
    SettlementResult,
)

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

# Money is stored to the paise (docs/00_PROJECT_BIBLE.md section 6: "INR /
# paise internally where needed"). Energy prices keep four decimals in
# `app.domain.policies.clearing_price`; an *amount* is a real sum of money and
# is quantised here, once, rather than wherever a multiplication happens.
AMOUNT_QUANTUM = Decimal("0.01")
# Energy keeps the four decimals every other kWh column in the schema uses.
ENERGY_QUANTUM = Decimal("0.0001")


def quantize_amount(value: Decimal) -> Decimal:
    """Round money to paise.

    Half-up rather than banker's rounding, for the same reason prices round
    half-up: money owed to a participant should round predictably, and
    half-even would make two economically identical settlements differ by a
    paisa depending on the parity of a digit.
    """
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def quantize_energy(value: Decimal) -> Decimal:
    return value.quantize(ENERGY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class SettlementPolicy:
    """Every rule and number reconciliation and accounting use.

    Kept in one object so that "what would change a settlement?" has a single
    answer, and so a real tariff or DISCOM rule arrives as data rather than as
    edits spread through the arithmetic.
    """

    # Bumped whenever any value here changes, because a stored settlement must
    # stay attributable to the rules that produced it.
    policy_version: str = "1.0.0"
    calculator_name: str = "standard_settlement"

    # ---- tolerance -------------------------------------------------------
    #
    # PROVISIONAL AND UNDOCUMENTED. How far actual delivery may differ from the
    # commitment before the difference is treated as a shortfall the grid had
    # to cover. No project document gives a band, and unlike the fee and the
    # balancing price there is no neutral value to fall back on: zero would
    # make every rounding error a penalty, and one would disable the mechanism
    # the architecture explicitly requires. 5 % is a placeholder pending a
    # ruling, not a derived figure.
    tolerance_fraction: Decimal = Decimal("0.05")

    # ---- balancing -------------------------------------------------------
    #
    # What undelivered energy costs the seller, as a multiple of the trade's
    # own effective price. Defaults to 1 — the shortfall is charged at exactly
    # the price it was sold at, which is the least-invented basis available. A
    # ruling that under-delivery should be penalised raises this above 1.
    balancing_price_multiplier: Decimal = ONE

    # ---- platform fee ----------------------------------------------------
    #
    # docs/04_DATA_MODEL.md entity 20 requires the column; no document gives a
    # rate. Defaults to zero, deliberately: a settlement that quietly skimmed
    # an invented percentage off every trade would be worse than one that
    # charges nothing until somebody decides otherwise.
    platform_fee_fraction: Decimal = ZERO

    def __post_init__(self) -> None:
        if not ZERO <= self.tolerance_fraction < ONE:
            raise ValueError("tolerance_fraction must lie in [0, 1)")
        if self.balancing_price_multiplier < ZERO:
            raise ValueError("balancing_price_multiplier must not be negative")
        if not ZERO <= self.platform_fee_fraction < ONE:
            raise ValueError("platform_fee_fraction must lie in [0, 1)")


DEFAULT_POLICY = SettlementPolicy()


# ---------------------------------------------------------------------------
# Reconciliation — energy only
# ---------------------------------------------------------------------------


def reconcile(
    *,
    committed_quantity_kwh: Decimal,
    actual: ActualEnergy,
    policy: SettlementPolicy = DEFAULT_POLICY,
) -> ReconciliationOutcome:
    """Compare what was delivered with what was agreed.

    Decides how much energy may be settled, and nothing about money.

    Unmeasured telemetry stops here. A window with no usable readings yields
    `AWAITING_TELEMETRY` and a `None` settled quantity — not a zero-delivery
    shortfall. The two are different facts, and only one of them is a seller's
    fault (docs/04_DATA_MODEL.md: NULL never means zero).
    """
    if not actual.is_measured:
        return ReconciliationOutcome(
            committed_quantity_kwh=committed_quantity_kwh,
            actual_quantity_kwh=None,
            deviation_kwh=None,
            deviation_pct=None,
            within_tolerance=False,
            balancing_kwh=ZERO,
            settled_quantity_kwh=None,
            status=ReconciliationStatus.AWAITING_TELEMETRY,
            reason=(
                "no usable telemetry covers the delivery window, so delivery cannot be "
                "compared with the commitment; this is not a zero-delivery shortfall"
            ),
            policy_version=policy.policy_version,
        )

    actual_kwh = quantize_energy(actual.quantity_kwh or ZERO)
    committed = quantize_energy(committed_quantity_kwh)
    deviation = quantize_energy(actual_kwh - committed)

    deviation_pct = quantize_energy(deviation / committed * HUNDRED) if committed > ZERO else None

    allowed = committed * policy.tolerance_fraction
    within = abs(deviation) <= allowed

    # Only the delivered energy can be paid for, and only up to what was
    # agreed: a seller who generated more than they sold did not sell more.
    settled = min(committed, actual_kwh)

    # Balancing covers the part of the commitment the buyer expected and the
    # seller did not deliver — the energy the distribution grid supplied
    # instead. Over-delivery creates none: the surplus was simply not traded.
    shortfall = max(committed - actual_kwh, ZERO)
    balancing = ZERO if within else quantize_energy(shortfall)

    return ReconciliationOutcome(
        committed_quantity_kwh=committed,
        actual_quantity_kwh=actual_kwh,
        deviation_kwh=deviation,
        deviation_pct=deviation_pct,
        within_tolerance=within,
        balancing_kwh=balancing,
        settled_quantity_kwh=settled,
        status=ReconciliationStatus.RECONCILED,
        reason=_describe(
            committed=committed,
            actual_kwh=actual_kwh,
            deviation=deviation,
            within=within,
            balancing=balancing,
            policy=policy,
            reading_count=actual.reading_count,
        ),
        policy_version=policy.policy_version,
    )


def _describe(
    *,
    committed: Decimal,
    actual_kwh: Decimal,
    deviation: Decimal,
    within: Decimal | bool,
    balancing: Decimal,
    policy: SettlementPolicy,
    reading_count: int,
) -> str:
    band = _trim(policy.tolerance_fraction * HUNDRED)
    measured = (
        f"{_trim(actual_kwh)} kWh measured against {_trim(committed)} kWh committed "
        f"from {reading_count} reading{'' if reading_count == 1 else 's'}"
    )
    if within:
        return f"{measured}; deviation {_trim(deviation)} kWh is within the {band}% tolerance"
    if balancing > ZERO:
        return (
            f"{measured}; shortfall of {_trim(balancing)} kWh exceeds the {band}% tolerance "
            "and is charged as balancing"
        )
    return (
        f"{measured}; over-delivery of {_trim(deviation)} kWh exceeds the {band}% tolerance "
        "but was not traded, so nothing is balanced"
    )


# ---------------------------------------------------------------------------
# Accounting — money only
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StandardSettlementCalculator:
    """The default `SettlementCalculator`.

    Satisfies the Protocol structurally — no inheritance — so a different set
    of rules is a different class and nothing else has to change. Holds its
    policy rather than reading it from anywhere, which is what lets two
    calculators with different tolerances coexist in one process.
    """

    policy: SettlementPolicy = field(default_factory=lambda: DEFAULT_POLICY)

    @property
    def name(self) -> str:
        return self.policy.calculator_name

    @property
    def policy_version(self) -> str:
        return self.policy.policy_version

    def settle(self, request: SettlementRequest) -> SettlementResult:
        outcome = reconcile(
            committed_quantity_kwh=request.committed_quantity_kwh,
            actual=request.actual,
            policy=self.policy,
        )
        price = request.effective_price.price_inr_per_kwh

        if outcome.settled_quantity_kwh is None:
            # Nothing measured: a settlement with no amounts and an explicit
            # reason. The zeros here are placeholders on an unfinished
            # settlement, never a claim that nothing was delivered — which is
            # why the service refuses to store this state as a final record.
            return self._empty(request, outcome, price)

        settled = outcome.settled_quantity_kwh
        gross = quantize_amount(settled * price)
        fee = quantize_amount(gross * self.policy.platform_fee_fraction)
        balancing_charge = quantize_amount(
            outcome.balancing_kwh * price * self.policy.balancing_price_multiplier
        )

        # The buyer pays for the energy actually delivered to them. The seller
        # receives that, less the platform's fee and less whatever the grid had
        # to supply in their place. The two sides differ by exactly what the
        # platform retained, which is what makes the ledger balance.
        buyer_debit = gross
        seller_credit = quantize_amount(gross - fee - balancing_charge)

        return SettlementResult(
            trade_id=request.trade_id,
            buyer_user_id=request.buyer_user_id,
            seller_user_id=request.seller_user_id,
            settled_quantity_kwh=settled,
            effective_price_inr_per_kwh=price,
            gross_amount_inr=gross,
            platform_fee_inr=fee,
            balancing_charge_inr=balancing_charge,
            buyer_debit_inr=buyer_debit,
            seller_credit_inr=seller_credit,
            status=SettlementStatus.SETTLED,
            policy_version=self.policy.policy_version,
            reconciliation=outcome,
            price_components_id=request.effective_price.source_id,
            forecast_basis_id=request.forecast_basis_id,
            grid_validation_id=request.grid_validation_id,
            lines=self._lines(outcome, price, gross, fee, balancing_charge),
        )

    def _empty(
        self, request: SettlementRequest, outcome: ReconciliationOutcome, price: Decimal
    ) -> SettlementResult:
        nil = quantize_amount(ZERO)
        return SettlementResult(
            trade_id=request.trade_id,
            buyer_user_id=request.buyer_user_id,
            seller_user_id=request.seller_user_id,
            settled_quantity_kwh=quantize_energy(ZERO),
            effective_price_inr_per_kwh=price,
            gross_amount_inr=nil,
            platform_fee_inr=nil,
            balancing_charge_inr=nil,
            buyer_debit_inr=nil,
            seller_credit_inr=nil,
            status=SettlementStatus.PENDING,
            policy_version=self.policy.policy_version,
            reconciliation=outcome,
            price_components_id=request.effective_price.source_id,
            forecast_basis_id=request.forecast_basis_id,
            grid_validation_id=request.grid_validation_id,
            lines=(),
        )

    def _lines(
        self,
        outcome: ReconciliationOutcome,
        price: Decimal,
        gross: Decimal,
        fee: Decimal,
        balancing_charge: Decimal,
    ) -> tuple[SettlementLine, ...]:
        lines = [
            SettlementLine(
                label="energy delivered",
                quantity_kwh=outcome.settled_quantity_kwh,
                price_inr_per_kwh=price,
                amount_inr=gross,
                reason="buyer pays for the energy actually delivered, at the effective price",
            )
        ]
        if fee > ZERO:
            lines.append(
                SettlementLine(
                    label="platform fee",
                    quantity_kwh=None,
                    price_inr_per_kwh=None,
                    amount_inr=fee,
                    reason=(
                        f"{_trim(self.policy.platform_fee_fraction * HUNDRED)}% of the gross "
                        "amount, retained from the seller's credit"
                    ),
                )
            )
        if balancing_charge > ZERO:
            lines.append(
                SettlementLine(
                    label="balancing charge",
                    quantity_kwh=outcome.balancing_kwh,
                    price_inr_per_kwh=quantize_amount(
                        price * self.policy.balancing_price_multiplier
                    ),
                    amount_inr=balancing_charge,
                    reason=(
                        "energy the seller committed and did not deliver, supplied by the "
                        "grid instead and charged to the seller"
                    ),
                )
            )
        return tuple(lines)


DEFAULT_CALCULATOR = StandardSettlementCalculator()


def _trim(value: Decimal) -> str:
    """Render a Decimal without trailing zeros, and without going through float."""
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
