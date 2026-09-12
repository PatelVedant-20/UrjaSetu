"""Phase 8 verification: emission, chain integrity and tamper detection.

Runs against the real table rather than in memory: the foundation's hashing was
correct in isolation and still could not store a payload, which is precisely the
class of defect only a database test finds.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.ledger import LocalFilePublisher
from app.db.models.audit import AuditEventRecord
from app.domain.enums import AuditEntityType, AuditEventType
from app.repositories.audit import AuditAppendOnlyError, AuditEventRepository
from app.services import audit_service, pricing_service, settlement_service
from app.services.settlement_service import NotReconcilableError

from .conftest import COMMITTED_KWH, Lifecycle


def _timeline(db_session: Session, lifecycle: Lifecycle) -> list[AuditEventRecord]:
    return audit_service.timeline(db_session, AuditEntityType.TRADE, lifecycle.trade.id)


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def test_pricing_and_settlement_emit_their_events(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """The foundation is useless if no service ever records anything."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)

    kinds = [row.event_type for row in _timeline(db_session, lifecycle)]

    assert AuditEventType.PRICE_CALCULATED in kinds
    assert (
        AuditEventType.TRADE_RECONCILED in kinds
    ), "settling records a reconciliation, so the timeline must contain one"
    assert AuditEventType.TRADE_SETTLED in kinds
    assert kinds.index(AuditEventType.TRADE_RECONCILED) < kinds.index(
        AuditEventType.TRADE_SETTLED
    ), "the timeline must read in the order the business events happened"


def test_a_refused_settlement_records_the_refusal_and_no_settlement(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """A failed business operation must not leave a successful-looking record."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)

    with pytest.raises(NotReconcilableError):
        settlement_service.settle_trade(db_session, lifecycle.trade.id)

    kinds = [row.event_type for row in _timeline(db_session, lifecycle)]
    assert AuditEventType.TRADE_RECONCILED in kinds
    assert (
        AuditEventType.TRADE_SETTLED not in kinds
    ), "no settlement happened, so nothing may claim one did"


def test_payloads_carry_domain_values_and_no_orm_objects(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)

    settled = next(
        row
        for row in _timeline(db_session, lifecycle)
        if row.event_type is AuditEventType.TRADE_SETTLED
    )
    payload = settled.payload_json

    assert payload["trade_id"] == str(lifecycle.trade.id)
    assert payload["payload_version"] == "1.0.0"
    assert payload["policy_version"] == "1.0.0"
    # Decimals survive as exact strings, never as floats.
    assert isinstance(payload["gross_amount_inr"], str)
    assert all(not isinstance(value, float) for value in payload.values())
    assert not any(
        key in payload for key in ("password", "token", "secret", "api_key")
    ), "audit payloads must never carry credentials"


# ---------------------------------------------------------------------------
# Chain integrity
# ---------------------------------------------------------------------------


def test_the_stored_chain_verifies(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """Hashes computed on the way in must reproduce from what was stored."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)

    verification = audit_service.verify(db_session)

    assert verification.intact, verification.summary
    assert verification.events_checked >= 3


def test_editing_a_stored_payload_breaks_verification(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """The property the whole phase exists for."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settled = settlement_service.settle_trade(db_session, lifecycle.trade.id)
    assert audit_service.verify(db_session).intact

    event = next(
        row
        for row in _timeline(db_session, lifecycle)
        if row.event_type is AuditEventType.TRADE_SETTLED
    )
    db_session.execute(
        text(
            "UPDATE audit_events SET payload_json = jsonb_set("
            "payload_json, '{settled_kwh}', '\"999.0000\"') WHERE id = :id"
        ),
        {"id": str(event.id)},
    )
    db_session.expire_all()

    verification = audit_service.verify(db_session)
    assert not verification.intact
    assert verification.broken_at_event_id == event.id
    assert settled.settled_kwh != Decimal("999.0000")


def test_editing_a_stored_timestamp_breaks_verification(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)

    event = _timeline(db_session, lifecycle)[0]
    db_session.execute(
        text("UPDATE audit_events SET event_time = event_time + interval '1 day' WHERE id = :id"),
        {"id": str(event.id)},
    )
    db_session.expire_all()

    assert not audit_service.verify(db_session).intact


def test_deleting_an_event_breaks_verification(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)

    middle = _timeline(db_session, lifecycle)[1]
    db_session.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": str(middle.id)})
    db_session.expire_all()

    assert not audit_service.verify(db_session).intact


# ---------------------------------------------------------------------------
# Append-only and fork resistance
# ---------------------------------------------------------------------------


def test_the_repository_refuses_to_delete(db_session: Session, lifecycle: Lifecycle) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    row = _timeline(db_session, lifecycle)[0]

    with pytest.raises(AuditAppendOnlyError):
        AuditEventRepository(db_session).delete(row)


def test_the_database_refuses_a_forked_chain(db_session: Session, lifecycle: Lifecycle) -> None:
    """Two events cannot claim the same predecessor."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    head = AuditEventRepository(db_session).latest()
    assert head is not None

    db_session.add(
        AuditEventRecord(
            event_type=head.event_type,
            entity_type=head.entity_type,
            entity_id=head.entity_id,
            event_time=head.event_time,
            recorded_at=head.recorded_at,
            payload_json={"forged": True},
            event_hash="f" * 64,
            previous_hash=head.previous_hash,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# Optional ledger
# ---------------------------------------------------------------------------


def test_anchoring_records_evidence_without_breaking_the_chain(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """The anchor is excluded from the hash, so publishing cannot invalidate it."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    event = _timeline(db_session, lifecycle)[0]

    anchored = audit_service.anchor_event(db_session, event.id, publisher=LocalFilePublisher())

    assert anchored.ledger_anchor_id is not None
    assert anchored.ledger_anchor_id.startswith("local:")
    assert audit_service.verify(db_session).intact


def test_a_failing_publisher_leaves_the_record_authoritative(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """A ledger outage must not corrupt PostgreSQL."""
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    event = _timeline(db_session, lifecycle)[0]

    class BrokenPublisher:
        name = "broken"

        def publish(self, event):  # type: ignore[no-untyped-def]
            raise RuntimeError("ledger unreachable")

    with pytest.raises(RuntimeError):
        audit_service.anchor_event(db_session, event.id, publisher=BrokenPublisher())

    # The publisher is called before anything is written, so a failure leaves
    # the row exactly as it was: still recorded, still unanchored, still
    # verifiable. The PostgreSQL record was authoritative all along.
    db_session.refresh(event)
    assert event.ledger_anchor_id is None
    assert AuditEventRepository(db_session).get(event.id) is not None
    assert audit_service.verify(db_session).intact
