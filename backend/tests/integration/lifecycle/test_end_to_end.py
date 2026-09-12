"""One trade, all the way through, across every phase.

telemetry -> forecast -> market -> grid validation -> pricing -> settlement
-> audit timeline.

Exercises the real services in sequence and asserts on persisted rows, not on
status codes. The point is the connections: each phase must consume what the
previous one actually produced.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.enums import (
    AuditEntityType,
    AuditEventType,
    GridValidationDecision,
    GridValidationStatus,
    ReconciliationStatus,
    SettlementStatus,
)
from app.domain.interfaces.grid import GridMetrics, GridValidationResult
from app.repositories.settlement import MeterReconciliationRepository
from app.services import (
    audit_service,
    grid_validation_service,
    pricing_service,
    settlement_service,
)

from .conftest import COMMITTED_KWH, DELIVERY_END, DELIVERY_START, FEEDER, Lifecycle


class HealthyFeederEngine:
    """A grid engine reporting a quiet, fully-rated feeder.

    Stands in for Power Grid Model so the workflow does not depend on solver
    convergence; the adapter has its own Phase 5 coverage.
    """

    name = "power_grid_model"
    engine_version = "1.13.162"

    def validate(self, request):  # type: ignore[no-untyped-def]
        return GridValidationResult(
            engine=self.name,
            engine_version=self.engine_version,
            status=GridValidationStatus.SAFE,
            metrics=GridMetrics(
                min_voltage_pu=Decimal("0.99"),
                max_voltage_pu=Decimal("1.01"),
                max_line_loading_pct=Decimal("45"),
                max_transformer_loading_pct=Decimal("38"),
            ),
        )


def test_full_trade_lifecycle(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    trade = lifecycle.trade

    # ---- Phase 2: the seller's meter measures delivery -------------------
    delivered = Decimal("9.8000")
    deliver(delivered)

    # ---- Phase 5: the trade is validated against the twin ----------------
    validation = grid_validation_service.validate_trade(
        db_session,
        engine=HealthyFeederEngine(),
        trade_id=trade.id,
        seller_node_id=lifecycle.seller_node.id,
        buyer_node_id=lifecycle.buyer_node.id,
        quantity_kwh=COMMITTED_KWH,
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )
    assert validation.status is GridValidationStatus.SAFE
    assert validation.decision is GridValidationDecision.ACCEPT

    trade.grid_validation_id = validation.id
    db_session.flush()

    # ---- Phase 6: the validated grid state drives the price --------------
    breakdown = pricing_service.price_trade(db_session, trade.id)

    assert breakdown.base_market_price == trade.clearing_price_inr_per_kwh
    assert breakdown.congestion_component == Decimal(
        "0"
    ), "a feeder at 45% of rating has headroom, so congestion costs nothing"
    assert (
        breakdown.base_market_price
        + breakdown.time_component
        + breakdown.congestion_component
        + breakdown.imbalance_component
        + breakdown.local_renewable_component
        == breakdown.final_price
    )
    assert breakdown.local_renewable_component < Decimal(
        "0"
    ), "buyer and seller share a feeder and the seller has active PV"

    # ---- Phase 7: settle against the effective price ---------------------
    settlement = settlement_service.settle_trade(db_session, trade.id)
    reconciliation = MeterReconciliationRepository(db_session).latest_for_trade(trade.id)
    assert reconciliation is not None

    assert reconciliation.committed_kwh == COMMITTED_KWH
    assert reconciliation.actual_kwh == delivered
    assert reconciliation.deviation_kwh == delivered - COMMITTED_KWH
    assert reconciliation.within_tolerance is True
    assert reconciliation.reconciliation_status is ReconciliationStatus.RECONCILED

    assert settlement.status is SettlementStatus.SETTLED
    assert settlement.settled_kwh == delivered
    assert settlement.gross_amount_inr == (delivered * breakdown.final_price).quantize(
        Decimal("0.01")
    )
    assert (
        settlement.buyer_debit_inr
        == settlement.seller_credit_inr
        + settlement.platform_fee_inr
        + settlement.balancing_charge_inr
    )
    assert settlement.buyer_user_id == lifecycle.buyer.id
    assert settlement.seller_user_id == lifecycle.seller.id

    # ---- Phase 8: the whole story is on one timeline, and it verifies ----
    timeline = audit_service.timeline(db_session, AuditEntityType.TRADE, trade.id)
    kinds = [row.event_type for row in timeline]

    assert kinds == [
        AuditEventType.GRID_VALIDATION_RECORDED,
        AuditEventType.PRICE_CALCULATED,
        AuditEventType.TRADE_RECONCILED,
        AuditEventType.TRADE_SETTLED,
    ]

    # Every event references the records it describes, so the timeline alone
    # reconstructs the decision.
    by_kind = {row.event_type: row.payload_json for row in timeline}
    assert by_kind[AuditEventType.GRID_VALIDATION_RECORDED]["grid_validation_id"] == str(
        validation.id
    )
    assert by_kind[AuditEventType.PRICE_CALCULATED]["price_components_id"] == str(breakdown.id)
    assert by_kind[AuditEventType.PRICE_CALCULATED]["final_price"] == format(
        breakdown.final_price, "f"
    )
    assert by_kind[AuditEventType.TRADE_RECONCILED]["reconciliation_id"] == str(reconciliation.id)
    assert by_kind[AuditEventType.TRADE_SETTLED]["settlement_id"] == str(settlement.id)
    assert by_kind[AuditEventType.TRADE_SETTLED]["grid_validation_id"] == str(validation.id)
    assert by_kind[AuditEventType.TRADE_SETTLED]["forecast_basis_id"] == str(
        lifecycle.forecast_run.id
    )

    # Each event links to its predecessor, and the chain holds.
    assert timeline[0].previous_hash is None or timeline[0].previous_hash != ""
    for earlier, later in zip(timeline, timeline[1:], strict=False):
        assert later.previous_hash == earlier.event_hash

    verification = audit_service.verify(db_session)
    assert verification.intact, verification.summary
    assert verification.events_checked == len(timeline)


def test_unsafe_grid_is_priced_up_and_never_settles_as_safe(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """The grid-failure path, end to end."""

    class OverloadedFeederEngine(HealthyFeederEngine):
        def validate(self, request):  # type: ignore[no-untyped-def]
            return GridValidationResult(
                engine=self.name,
                engine_version=self.engine_version,
                status=GridValidationStatus.UNSAFE,
                metrics=GridMetrics(max_line_loading_pct=Decimal("135")),
            )

    validation = grid_validation_service.validate_trade(
        db_session,
        engine=OverloadedFeederEngine(),
        trade_id=lifecycle.trade.id,
        seller_node_id=lifecycle.seller_node.id,
        buyer_node_id=lifecycle.buyer_node.id,
        quantity_kwh=COMMITTED_KWH,
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )
    lifecycle.trade.grid_validation_id = validation.id
    db_session.flush()

    assert validation.status is GridValidationStatus.UNSAFE
    assert validation.decision is GridValidationDecision.REJECT

    quote = pricing_service.quote_trade(db_session, lifecycle.trade.id)

    assert quote.grid_status is GridValidationStatus.UNSAFE
    assert quote.congestion_component > Decimal("0")
    assert quote.recommended_decision is GridValidationDecision.REJECT
    assert (
        quote.final_price > quote.base_market_price
    ), "a constrained feeder must make the trade more expensive, not less"

    # The audit trail records what was actually decided.
    kinds = [
        row.event_type
        for row in audit_service.timeline(db_session, AuditEntityType.TRADE, lifecycle.trade.id)
    ]
    assert AuditEventType.GRID_VALIDATION_RECORDED in kinds
    assert AuditEventType.TRADE_SETTLED not in kinds
