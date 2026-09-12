"""Phase 9 verification: the audit ledger's own guarantees.

docs/07_CODING_PHASES.md, Phase 9 gate: "All material trade/settlement events
produce verifiable audit records."

Three things are checked here that the lifecycle tests do not: that the *market*
end of the lifecycle emits at all, that every class of tampering the ledger
claims to detect actually is detected, and that a rolled-back business
transaction leaves no audit record behind claiming it happened.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models.audit import AuditEventRecord
from app.domain.enums import (
    AuditEntityType,
    AuditEventType,
    GridValidationStatus,
    OrderSide,
)
from app.domain.interfaces.grid import GridMetrics, GridValidationResult
from app.domain.policies.audit_chain import canonical_json, event_fingerprint, seal
from app.repositories.audit import AuditEventRepository
from app.services import (
    audit_service,
    grid_validation_service,
    market_service,
    pricing_service,
    settlement_service,
)
from app.services.grid_validation_service import GridEngineError
from app.services.settlement_service import NotReconcilableError

from .conftest import (
    COMMITTED_KWH,
    DELIVERY_END,
    DELIVERY_START,
    FEEDER,
    Lifecycle,
)


class _SafeEngine:
    name = "power_grid_model"
    engine_version = "1.13.162"

    def validate(self, request):  # type: ignore[no-untyped-def]
        return GridValidationResult(
            engine=self.name,
            engine_version=self.engine_version,
            status=GridValidationStatus.SAFE,
            metrics=GridMetrics(max_line_loading_pct=Decimal("45")),
        )


def _events(db_session: Session) -> list[AuditEventRecord]:
    return list(AuditEventRepository(db_session).list_chain())


# ---------------------------------------------------------------------------
# Emission at the market end of the lifecycle
# ---------------------------------------------------------------------------


def test_placing_an_order_is_audited(db_session: Session, lifecycle: Lifecycle) -> None:
    """Through the real service, including its eligibility and surplus gates."""
    order = market_service.place_order(
        db_session,
        market_session_id=lifecycle.market_session.id,
        user_id=lifecycle.seller.id,
        site_id=lifecycle.seller_site.id,
        side=OrderSide.SELL,
        energy_kwh=Decimal("5.0000"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        min_price_inr_per_kwh=Decimal("4.0000"),
        node_id=lifecycle.seller_node.id,
        forecast_basis_id=lifecycle.forecast_run.id,
    )

    timeline = audit_service.timeline(db_session, AuditEntityType.ORDER, order.id)

    assert [row.event_type for row in timeline] == [AuditEventType.ORDER_PLACED]
    assert timeline[0].payload_json["order_id"] == str(order.id)
    assert timeline[0].payload_json["side"] == "sell"
    assert timeline[0].actor_user_id == lifecycle.seller.id


def test_clearing_a_session_audits_the_clearing_and_each_trade(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """A whole market session driven through the real services.

    Uses its own session rather than the fixture's, because the fixture already
    holds a matched trade for that order pair and Phase 4 correctly refuses to
    clear the same pairing twice.
    """
    from tests.integration.phase4.conftest import StubMatchingEngine  # noqa: PLC0415

    market = market_service.open_session(db_session, market_date=date(2026, 6, 3))
    for side, price_field in (
        (OrderSide.SELL, {"min_price_inr_per_kwh": Decimal("4.0000")}),
        (OrderSide.BUY, {"max_price_inr_per_kwh": Decimal("8.0000")}),
    ):
        seller_side = side is OrderSide.SELL
        market_service.place_order(
            db_session,
            market_session_id=market.id,
            user_id=(lifecycle.seller if seller_side else lifecycle.buyer).id,
            site_id=(lifecycle.seller_site if seller_side else lifecycle.buyer_site).id,
            side=side,
            energy_kwh=Decimal("5.0000"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            node_id=(lifecycle.seller_node if seller_side else lifecycle.buyer_node).id,
            forecast_basis_id=lifecycle.forecast_run.id if seller_side else None,
            **price_field,
        )

    # Clearing follows closing: the market service enforces that order, and the
    # test respects it rather than reaching past it.
    market_service.close_session(db_session, market.id)
    trades = market_service.clear_session(db_session, market.id, engine=StubMatchingEngine())

    placed = [r for r in _events(db_session) if r.event_type is AuditEventType.ORDER_PLACED]
    assert len(placed) == 2, "both orders must be audited"

    cleared = audit_service.timeline(db_session, AuditEntityType.MARKET_SESSION, market.id)
    assert [row.event_type for row in cleared] == [AuditEventType.MARKET_CLEARED]
    assert cleared[0].actor_user_id is None, "clearing is platform-initiated"
    assert cleared[0].payload_json["trade_count"] == len(trades)

    for trade in trades:
        kinds = [
            row.event_type
            for row in audit_service.timeline(db_session, AuditEntityType.TRADE, trade.id)
        ]
        assert AuditEventType.TRADE_PROPOSED in kinds

    assert audit_service.verify(db_session).intact


def test_a_failed_grid_validation_is_still_audited(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """An unavailable solver is a fact about the trade, and is recorded."""

    class FailingEngine(_SafeEngine):
        def validate(self, request):  # type: ignore[no-untyped-def]
            raise RuntimeError("power flow did not converge")

    with pytest.raises(GridEngineError):
        grid_validation_service.validate_trade(
            db_session,
            engine=FailingEngine(),
            trade_id=lifecycle.trade.id,
            seller_node_id=lifecycle.seller_node.id,
            buyer_node_id=lifecycle.buyer_node.id,
            quantity_kwh=COMMITTED_KWH,
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            feeder_id=FEEDER,
        )

    timeline = audit_service.timeline(db_session, AuditEntityType.TRADE, lifecycle.trade.id)
    recorded = [r for r in timeline if r.event_type is AuditEventType.GRID_VALIDATION_RECORDED]
    assert len(recorded) == 1
    assert recorded[0].payload_json["grid_status"] == GridValidationStatus.UNKNOWN.value


# ---------------------------------------------------------------------------
# The full tamper matrix
# ---------------------------------------------------------------------------


@pytest.fixture
def chained(db_session: Session, lifecycle: Lifecycle, deliver: Callable[..., None]) -> Session:
    """Three linked events from real business operations."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)
    assert audit_service.verify(db_session).intact
    return db_session


def test_rewriting_a_stored_event_hash_is_detected(chained: Session) -> None:
    victim = _events(chained)[1]
    chained.execute(
        text("UPDATE audit_events SET event_hash = :h WHERE id = :id"),
        {"h": "a" * 64, "id": str(victim.id)},
    )
    chained.expire_all()

    result = audit_service.verify(chained)
    assert not result.intact
    assert result.broken_at_event_id == victim.id


def test_rewriting_a_stored_previous_hash_is_detected(chained: Session) -> None:
    victim = _events(chained)[1]
    chained.execute(
        text("UPDATE audit_events SET previous_hash = :h WHERE id = :id"),
        {"h": "b" * 64, "id": str(victim.id)},
    )
    chained.expire_all()

    assert not audit_service.verify(chained).intact


def test_reordering_events_is_detected(chained: Session) -> None:
    """Order is part of what is verified, so it is never re-sorted away."""
    events = _events(chained)
    first, second = events[0], events[1]
    chained.execute(
        text("UPDATE audit_events SET recorded_at = :t WHERE id = :id"),
        {"t": second.recorded_at + timedelta(seconds=5), "id": str(first.id)},
    )
    chained.expire_all()

    assert not audit_service.verify(chained).intact


def test_truncating_the_start_of_the_chain_is_detected(chained: Session) -> None:
    genesis = _events(chained)[0]
    chained.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": str(genesis.id)})
    chained.expire_all()

    result = audit_service.verify(chained)
    assert not result.intact
    assert "genesis" in result.summary or "missing" in result.summary


def test_an_untampered_chain_still_verifies_after_all_of_that(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[..., None]
) -> None:
    """The control case: verification is not simply always failing."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)

    result = audit_service.verify(db_session)
    assert result.intact, result.summary


# ---------------------------------------------------------------------------
# Deterministic serialization
# ---------------------------------------------------------------------------


def test_hashing_the_same_event_twice_is_stable(db_session: Session, lifecycle: Lifecycle) -> None:
    event = audit_service.build_event(
        event_type=AuditEventType.TRADE_PROPOSED,
        entity_id=lifecycle.trade.id,
        payload={"quantity_kwh": Decimal("10.0000"), "trade_id": lifecycle.trade.id},
        occurred_at=DELIVERY_START,
    )

    assert event_fingerprint(event, None) == event_fingerprint(event, None)
    assert seal(event, None).event_hash == event_fingerprint(event, None)


def test_key_order_does_not_change_the_serialization() -> None:
    a = {"b": Decimal("1.50"), "a": uuid.UUID(int=1)}
    b = {"a": uuid.UUID(int=1), "b": Decimal("1.50")}

    assert canonical_json(a) == canonical_json(b)


def test_a_float_in_a_payload_is_refused(db_session: Session, lifecycle: Lifecycle) -> None:
    """Binary floating point must never reach a financial hash."""
    event = audit_service.build_event(
        event_type=AuditEventType.TRADE_PROPOSED,
        entity_id=lifecycle.trade.id,
        payload={"quantity_kwh": 10.5},
        occurred_at=DELIVERY_START,
    )

    with pytest.raises(TypeError, match="float"):
        audit_service.record(db_session, event)


def test_an_unsupported_type_fails_loudly(db_session: Session, lifecycle: Lifecycle) -> None:
    """Unknown objects are never silently stringified."""
    event = audit_service.build_event(
        event_type=AuditEventType.TRADE_PROPOSED,
        entity_id=lifecycle.trade.id,
        payload={"trade": object()},
        occurred_at=DELIVERY_START,
    )

    with pytest.raises(TypeError):
        audit_service.record(db_session, event)


# ---------------------------------------------------------------------------
# Transaction semantics
# ---------------------------------------------------------------------------


def test_a_rolled_back_operation_leaves_no_audit_record(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """The property the settlement transaction depends on.

    `record` joins the caller's transaction rather than committing its own, so
    an event cannot survive the failure of the thing it describes.
    """
    before = len(_events(db_session))

    db_session.begin_nested()
    audit_service.record(
        db_session,
        audit_service.build_event(
            event_type=AuditEventType.TRADE_PROPOSED,
            entity_id=lifecycle.trade.id,
            payload={"trade_id": lifecycle.trade.id},
            occurred_at=DELIVERY_START,
        ),
    )
    assert len(_events(db_session)) == before + 1
    db_session.rollback()

    assert (
        len(_events(db_session)) == before
    ), "an audit event must not outlive the transaction that produced it"


def test_a_refused_settlement_leaves_no_settled_event(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)

    with pytest.raises(NotReconcilableError):
        settlement_service.settle_trade(db_session, lifecycle.trade.id)

    kinds = [
        row.event_type
        for row in audit_service.timeline(db_session, AuditEntityType.TRADE, lifecycle.trade.id)
    ]
    assert AuditEventType.TRADE_SETTLED not in kinds
    assert AuditEventType.TRADE_RECONCILED in kinds


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def test_the_timeline_alone_reconstructs_the_trade(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[..., None]
) -> None:
    """Replay: the audit log is sufficient to restate what happened.

    Every figure asserted here is read back out of the audit payloads, not out
    of the business tables, which is what makes the ledger an independent
    record rather than a second copy of the same rows.
    """
    grid_validation_service.validate_trade(
        db_session,
        engine=_SafeEngine(),
        trade_id=lifecycle.trade.id,
        seller_node_id=lifecycle.seller_node.id,
        buyer_node_id=lifecycle.buyer_node.id,
        quantity_kwh=COMMITTED_KWH,
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )
    breakdown = pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(Decimal("9.8000"))
    settlement = settlement_service.settle_trade(db_session, lifecycle.trade.id)

    replay = {
        row.event_type: row.payload_json
        for row in audit_service.timeline(db_session, AuditEntityType.TRADE, lifecycle.trade.id)
    }

    assert replay[AuditEventType.GRID_VALIDATION_RECORDED]["grid_status"] == "safe"
    assert replay[AuditEventType.PRICE_CALCULATED]["final_price"] == format(
        breakdown.final_price, "f"
    )
    assert replay[AuditEventType.PRICE_CALCULATED]["formula_version"] == breakdown.formula_version
    assert replay[AuditEventType.TRADE_RECONCILED]["actual_kwh"] == "9.8000"
    assert replay[AuditEventType.TRADE_RECONCILED]["committed_kwh"] == format(COMMITTED_KWH, "f")
    assert replay[AuditEventType.TRADE_SETTLED]["settled_kwh"] == format(
        settlement.settled_kwh, "f"
    )
    assert replay[AuditEventType.TRADE_SETTLED]["buyer_debit_inr"] == format(
        settlement.buyer_debit_inr, "f"
    )
    assert replay[AuditEventType.TRADE_SETTLED]["policy_version"] == "1.0.0"
