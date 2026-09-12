"""Settlement orchestration.

    trade -> effective price + actual energy -> reconcile -> settle -> record

Owns the transaction boundary and the assembly of everything a settlement
depends on. It contains **no tolerance, no fee and no accounting arithmetic**:
it gathers inputs from their canonical owners, calls the calculator, checks the
result at the boundary and records it.

docs/04_DATA_MODEL.md fixes the transaction boundary for this phase:
"Settlement — single transaction: reconciliation, settlement row, balance/ledger
entries if balances are introduced, audit event." Reconciliation and the
settlement row are written together here. The audit event belongs to Phase 8,
which owns `audit_events`; this phase produces the data it will anchor.

**What it consumes, and from where**

* the **effective price** through `EffectivePriceResolver`, backed by the
  Phase 6 pricing service — never recomputed, never re-derived from the Phase 4
  clearing price;
* **actual energy** through `ActualEnergyResolver`, backed by the Phase 2
  telemetry service — never by reading meter rows directly;
* the **commitment** from the Phase 4 trade;
* the **forecast basis** from the Phase 3 run the sell order cites, carried for
  traceability only.

Both dependencies are Protocols, so Phase 6's API work landing later, or
telemetry gaining a better aggregate, changes nothing in this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models.market import Order, Trade
from app.db.models.settlement import MeterReconciliation, Settlement
from app.domain.enums import ReconciliationStatus, SettlementStatus
from app.domain.interfaces.settlement import (
    ActualEnergy,
    ActualEnergyResolver,
    EffectivePrice,
    EffectivePriceResolver,
    SettlementCalculator,
    SettlementRequest,
    SettlementResult,
)
from app.domain.policies.settlement import DEFAULT_CALCULATOR
from app.repositories import ForecastPointRepository, TradeRepository
from app.repositories.settlement import (
    MeterReconciliationRepository,
    SettlementRepository,
)
from app.services import audit_service, pricing_service, telemetry_service

ZERO = Decimal("0")


class SettlementError(UnprocessableError):
    """A settlement could not be produced, or a calculator misbehaved."""

    code = "SETTLEMENT_FAILED"


class NotReconcilableError(UnprocessableError):
    """Actual delivery is not yet known, so there is nothing final to settle."""

    code = "SETTLEMENT_NOT_RECONCILABLE"


# ---------------------------------------------------------------------------
# Dependency boundaries, satisfied by the canonical upstream services
# ---------------------------------------------------------------------------


class PricingServicePriceResolver:
    """Reads the Phase 6 effective price from the stored breakdown.

    `price_components.final_price`, not `trades.clearing_price_inr_per_kwh`.
    The Phase 6 handoff identified this as the decision Phase 7 had to make
    explicitly: the clearing price is the Phase 4 market baseline, and settling
    against it would silently discard every dynamic component.

    Raises rather than falling back. A settlement that quietly used the wrong
    price would be indistinguishable from a correct one.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def effective_price_for(self, trade_id: UUID) -> EffectivePrice:
        breakdown = pricing_service.get_breakdown(self._session, trade_id)
        return EffectivePrice(
            price_inr_per_kwh=breakdown.final_price,
            source_id=breakdown.id,
            formula_version=breakdown.formula_version,
        )


class TelemetryActualEnergyResolver:
    """Reads measured delivery from the Phase 2 telemetry service.

    Uses the service's own aggregation, which applies the existing quality
    policy — only readings classified `valid` are summed, so a stale or invalid
    reading is never laundered into an actual. Settlement does not reclassify
    anything and does not touch `telemetry_readings` directly.

    A window whose readings carry no energy at all, or that holds no usable
    readings, comes back unmeasured rather than as zero.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def actual_energy_for(self, *, site_id: UUID, start: datetime, end: datetime) -> ActualEnergy:
        buckets = telemetry_service.get_interval_for_site(
            self._session, site_id, start=start, end=end, resolution=end - start
        )
        total: Decimal | None = None
        readings = 0
        for bucket in buckets:
            readings += getattr(bucket, "reading_count", 0)
            energy = getattr(bucket, "energy_kwh", None)
            if energy is not None:
                total = energy if total is None else total + energy

        return ActualEnergy(
            window_start=start,
            window_end=end,
            quantity_kwh=total,
            reading_count=readings,
            source="telemetry:valid-only",
        )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile_trade(
    session: Session,
    trade_id: UUID,
    *,
    calculator: SettlementCalculator = DEFAULT_CALCULATOR,
    price_resolver: EffectivePriceResolver | None = None,
    energy_resolver: ActualEnergyResolver | None = None,
) -> MeterReconciliation:
    """Compare actual delivery with the commitment, and record it.

    Backs `POST /trades/{trade_id}/reconcile`. Always writes a row, including
    when nothing could be measured: the record that the question was asked is
    itself worth keeping.
    """
    result = _calculate(
        session,
        trade_id,
        calculator=calculator,
        price_resolver=price_resolver,
        energy_resolver=energy_resolver,
    )
    row = _record_reconciliation(session, trade_id, result)
    session.commit()
    session.refresh(row)
    return row


def preview_settlement(
    session: Session,
    trade_id: UUID,
    *,
    calculator: SettlementCalculator = DEFAULT_CALCULATOR,
    price_resolver: EffectivePriceResolver | None = None,
    energy_resolver: ActualEnergyResolver | None = None,
) -> SettlementResult:
    """Compute a settlement without storing anything.

    The read-only path: what *would* be settled, including the `pending` result
    for a trade whose delivery has not been measured yet.
    """
    return _calculate(
        session,
        trade_id,
        calculator=calculator,
        price_resolver=price_resolver,
        energy_resolver=energy_resolver,
    )


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------


def settle_trade(
    session: Session,
    trade_id: UUID,
    *,
    calculator: SettlementCalculator = DEFAULT_CALCULATOR,
    price_resolver: EffectivePriceResolver | None = None,
    energy_resolver: ActualEnergyResolver | None = None,
    at: datetime | None = None,
) -> Settlement:
    """Reconcile and settle a trade. One transaction.

    Backs `POST /trades/{trade_id}/settle`, which docs/05_API_SPEC.md defines
    as creating the final settlement "after reconciliation rules are
    satisfied" — so a trade whose delivery is still unmeasured is refused here
    rather than stored as a settlement of zero.

    Re-settling appends. Any settlement already standing for this trade is
    marked `superseded` and a new row is written, so a correction leaves the
    earlier figures readable instead of destroying them.
    """
    moment = at or datetime.now(UTC)
    result = _calculate(
        session,
        trade_id,
        calculator=calculator,
        price_resolver=price_resolver,
        energy_resolver=energy_resolver,
    )

    # The reconciliation is recorded either way: it is the evidence for
    # whatever the settlement claims, and refusing to settle is itself an
    # outcome worth being able to explain afterwards.
    _record_reconciliation(session, trade_id, result)

    if not result.reconciliation.is_complete:
        session.commit()
        raise NotReconcilableError(
            "Actual delivery for this trade has not been measured, so it cannot be settled.",
            details={
                "trade_id": str(trade_id),
                "reconciliation_status": result.reconciliation.status.value,
                "reason": result.reconciliation.reason,
            },
        )

    _validate_result(result, calculator)

    settlements = SettlementRepository(session)
    for existing in settlements.list_for_trade(trade_id):
        if existing.status is SettlementStatus.SETTLED:
            existing.status = SettlementStatus.SUPERSEDED

    row = Settlement(
        trade_id=result.trade_id,
        buyer_user_id=result.buyer_user_id,
        seller_user_id=result.seller_user_id,
        settled_kwh=result.settled_quantity_kwh,
        gross_amount_inr=result.gross_amount_inr,
        platform_fee_inr=result.platform_fee_inr,
        balancing_charge_inr=result.balancing_charge_inr,
        seller_credit_inr=result.seller_credit_inr,
        buyer_debit_inr=result.buyer_debit_inr,
        status=SettlementStatus.SETTLED,
        settled_at=moment,
    )
    settlements.add(row)
    session.flush()
    audit_service.record(
        session,
        audit_service.trade_settled(
            trade_id=result.trade_id,
            settlement_id=row.id,
            buyer_user_id=result.buyer_user_id,
            seller_user_id=result.seller_user_id,
            settled_kwh=result.settled_quantity_kwh,
            gross_amount_inr=result.gross_amount_inr,
            platform_fee_inr=result.platform_fee_inr,
            balancing_charge_inr=result.balancing_charge_inr,
            buyer_debit_inr=result.buyer_debit_inr,
            seller_credit_inr=result.seller_credit_inr,
            policy_version=result.policy_version,
            price_components_id=result.price_components_id,
            grid_validation_id=result.grid_validation_id,
            forecast_basis_id=result.forecast_basis_id,
            occurred_at=moment,
        ),
    )
    session.commit()
    session.refresh(row)
    return row


def get_settlement(session: Session, settlement_id: UUID) -> Settlement:
    """Backs `GET /settlements/{settlement_id}`."""
    row = SettlementRepository(session).get(settlement_id)
    if row is None:
        raise NotFoundError(
            "Settlement not found.",
            code="SETTLEMENT_NOT_FOUND",
            details={"settlement_id": str(settlement_id)},
        )
    return row


def list_settlements_for_user(session: Session, user_id: UUID) -> list[Settlement]:
    """Backs `GET /users/{user_id}/settlements`."""
    return list(SettlementRepository(session).list_for_user(user_id))


def active_settlement_for_trade(session: Session, trade_id: UUID) -> Settlement | None:
    """The settlement that currently stands for a trade, if any."""
    return SettlementRepository(session).active_for_trade(trade_id)


# ---------------------------------------------------------------------------
# Assembling the inputs
# ---------------------------------------------------------------------------


def build_request(
    session: Session,
    trade: Trade,
    *,
    price_resolver: EffectivePriceResolver,
    energy_resolver: ActualEnergyResolver,
) -> SettlementRequest:
    """Collect everything a settlement depends on, from its canonical owner.

    The four quantities stay distinct here and downstream: the trade supplies
    what was **agreed**, the forecast run what was **predicted**, telemetry what
    **actually happened**, and only the reconciliation policy decides what is
    **settled**.
    """
    buy_order = session.get(Order, trade.buy_order_id)
    sell_order = session.get(Order, trade.sell_order_id)
    if buy_order is None or sell_order is None:
        raise SettlementError(
            "The trade's orders are missing, so its parties cannot be identified.",
            details={"trade_id": str(trade.id)},
        )

    return SettlementRequest(
        trade_id=trade.id,
        buyer_user_id=buy_order.user_id,
        seller_user_id=sell_order.user_id,
        committed_quantity_kwh=trade.quantity_kwh,
        effective_price=price_resolver.effective_price_for(trade.id),
        delivery_start=trade.delivery_start,
        delivery_end=trade.delivery_end,
        actual=energy_resolver.actual_energy_for(
            site_id=sell_order.site_id,
            start=trade.delivery_start,
            end=trade.delivery_end,
        ),
        forecast_quantity_kwh=_forecast_quantity(session, sell_order, trade),
        forecast_basis_id=sell_order.forecast_basis_id,
        grid_validation_id=trade.grid_validation_id,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _forecast_quantity(session: Session, sell_order: Order, trade: Trade) -> Decimal | None:
    """What the seller's forecast predicted over the delivery window.

    Explanation and traceability only — nobody is paid on a prediction, and
    this value never reaches the accounting. It is what lets a reconciliation
    say whether a shortfall was already visible in the forecast the trade was
    sold against.

    `None` when the order cites no forecast, or when the run's points carry no
    predicted energy: an absent prediction is not a prediction of zero.
    """
    if sell_order.forecast_basis_id is None:
        return None

    points = ForecastPointRepository(session).list_for_run(sell_order.forecast_basis_id)
    covering = [
        point.predicted_kwh
        for point in points
        if point.predicted_kwh is not None
        and point.interval_start < trade.delivery_end
        and point.interval_end > trade.delivery_start
    ]
    return sum(covering, ZERO) if covering else None


def _calculate(
    session: Session,
    trade_id: UUID,
    *,
    calculator: SettlementCalculator,
    price_resolver: EffectivePriceResolver | None,
    energy_resolver: ActualEnergyResolver | None,
) -> SettlementResult:
    trade = _get_trade(session, trade_id)
    request = build_request(
        session,
        trade,
        price_resolver=price_resolver or PricingServicePriceResolver(session),
        energy_resolver=energy_resolver or TelemetryActualEnergyResolver(session),
    )
    try:
        return calculator.settle(request)
    except Exception as exc:
        raise SettlementError(
            f"Settlement calculator {calculator.name!r} failed.",
            details={"trade_id": str(trade_id), "reason": exc.__class__.__name__},
        ) from exc


def _record_reconciliation(
    session: Session, trade_id: UUID, result: SettlementResult
) -> MeterReconciliation:
    """Write the comparison and audit it, as one indivisible act.

    Both callers — `reconcile_trade` and `settle_trade` — record a
    reconciliation, so the audit event is emitted here rather than at each call
    site. Emitting it at one of them meant a trade settled directly lost the
    reconciliation step from its audit timeline, and a settlement refused for
    missing telemetry left no audit trace of the refusal at all.

    Joins the caller's transaction and does not commit.
    """
    outcome = result.reconciliation
    row = MeterReconciliation(
        # See `pricing_service.price_trade`: the column default is the
        # transaction clock, which cannot order two rows written together.
        created_at=datetime.now(UTC),
        trade_id=trade_id,
        committed_kwh=outcome.committed_quantity_kwh,
        actual_kwh=outcome.actual_quantity_kwh,
        deviation_kwh=outcome.deviation_kwh,
        within_tolerance=outcome.within_tolerance,
        balancing_kwh=outcome.balancing_kwh,
        reconciliation_status=outcome.status,
        reason=outcome.reason,
    )
    MeterReconciliationRepository(session).add(row)
    session.flush()

    audit_service.record(
        session,
        audit_service.trade_reconciled(
            trade_id=trade_id,
            reconciliation_id=row.id,
            committed_kwh=row.committed_kwh,
            actual_kwh=row.actual_kwh,
            deviation_kwh=row.deviation_kwh,
            within_tolerance=row.within_tolerance,
            balancing_kwh=row.balancing_kwh,
            reconciliation_status=row.reconciliation_status.value,
            policy_version=outcome.policy_version,
            forecast_basis_id=result.forecast_basis_id,
            occurred_at=row.created_at or datetime.now(UTC),
        ),
    )
    return row


def _get_trade(session: Session, trade_id: UUID) -> Trade:
    trade = TradeRepository(session).get(trade_id)
    if trade is None:
        raise NotFoundError(
            "Trade not found.", code="TRADE_NOT_FOUND", details={"trade_id": str(trade_id)}
        )
    return trade


def _validate_result(result: SettlementResult, calculator: SettlementCalculator) -> None:
    """Check a calculator's output before any money is recorded.

    The first case is the important one: a settlement whose two sides disagree
    is not a settlement. The database enforces the same identity, but failing
    here names the calculator instead of surfacing a constraint violation from
    three layers down.
    """
    if not result.ledger_balances:
        raise SettlementError(
            "Calculator returned a settlement whose ledger does not balance.",
            details={
                "calculator": calculator.name,
                "buyer_debit_inr": str(result.buyer_debit_inr),
                "seller_credit_inr": str(result.seller_credit_inr),
                "retained_inr": str(result.platform_retained_inr),
            },
        )
    if result.settled_quantity_kwh < ZERO or result.gross_amount_inr < ZERO:
        raise SettlementError(
            "Calculator returned a negative settled quantity or gross amount.",
            details={"calculator": calculator.name},
        )
    if result.reconciliation.status is not ReconciliationStatus.RECONCILED:
        raise SettlementError(
            "Calculator returned a final settlement for an unreconciled trade.",
            details={"calculator": calculator.name},
        )
    if not result.policy_version:
        raise SettlementError(
            "Calculator returned a settlement with no policy version.",
            details={"calculator": calculator.name},
        )
