"""Audit orchestration.

    domain action -> AuditEvent -> seal against the chain head -> audit_events
                                                              -> optional ledger

Owns appending, verification and anchoring. It contains **no hashing and no
serialization** — those are in `app.domain.policies.audit_chain` — and it
contains no business rules at all: it records what other phases decided, and
never decides anything itself.

--------------------------------------------------------------------------
TRANSACTION POLICY
--------------------------------------------------------------------------
`record` **does not commit.** The audit event joins the caller's transaction
and is flushed into it, which makes three things true:

* docs/04_DATA_MODEL.md requires settlement to be a single transaction
  containing "reconciliation, settlement row, ... audit event" — this is how
  that holds;
* if the business operation rolls back, its audit event rolls back with it. An
  audit log describing something that did not happen is worse than one missing
  an entry;
* if the audit append fails, the business operation fails with it. Audit
  failures are never swallowed.

**Ledger publication is the opposite**: outside the transaction, optional, and
isolated. A publisher outage cannot stop a trade from settling, because by then
the authoritative record already exists in PostgreSQL.

--------------------------------------------------------------------------
CONCURRENCY
--------------------------------------------------------------------------
The chain is global, so two events appended concurrently both read the same
head and both claim the same predecessor. The second loses on
`uq_audit_events_previous_hash` and its transaction must be retried. That is
the intended behaviour: the database refuses to let the chain fork, rather than
the application hoping it will not.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models.audit import AuditEventRecord
from app.domain.enums import (
    AuditEntityType,
    AuditEventType,
    GridValidationStatus,
)
from app.domain.interfaces.audit import (
    AuditEvent,
    ChainVerification,
    DLTPublisher,
    SealedAuditEvent,
)
from app.domain.policies.audit_chain import seal, verify_chain
from app.repositories.audit import AuditEventRepository


class AuditError(UnprocessableError):
    """An audit event could not be recorded."""

    code = "AUDIT_FAILED"


# ---------------------------------------------------------------------------
# Appending
# ---------------------------------------------------------------------------


def record(session: Session, event: AuditEvent) -> AuditEventRecord:
    """Append one event to the chain, inside the caller's transaction.

    Seals the event against the current head and flushes it, so a second event
    recorded later in the same transaction links to this one rather than to
    what the head was when the transaction began.

    Does not commit. See the module's transaction policy.
    """
    repository = AuditEventRepository(session)
    head = repository.latest()
    sealed = seal(event, head.event_hash if head is not None else None)

    record_row = AuditEventRecord(
        id=event.event_id,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        event_time=event.event_time,
        recorded_at=event.recorded_at,
        actor_user_id=event.actor_user_id,
        payload_json=event.with_payload_version(),
        event_hash=sealed.event_hash,
        previous_hash=sealed.previous_hash,
    )
    repository.add(record_row)
    session.flush()
    return record_row


def build_event(
    *,
    event_type: AuditEventType,
    entity_id: UUID,
    payload: Mapping[str, object],
    occurred_at: datetime,
    actor_user_id: UUID | None = None,
    recorded_at: datetime | None = None,
) -> AuditEvent:
    """Assemble a canonical event.

    The entity type is derived from the event type rather than passed in, so a
    caller cannot record a settlement against an order by mistake.
    """
    return AuditEvent(
        event_id=uuid4(),
        event_type=event_type,
        entity_type=event_type.subject,
        entity_id=entity_id,
        event_time=occurred_at,
        recorded_at=recorded_at or datetime.now(UTC),
        actor_user_id=actor_user_id,
        payload=dict(payload),
    )


# ---------------------------------------------------------------------------
# Event builders for the phases that emit them
# ---------------------------------------------------------------------------
#
# Each takes plain values, never ORM objects, so a business service can call it
# with what it already has and the audit layer stays uncoupled from any phase's
# internals. Payloads carry stable identifiers and decision values only — never
# credentials, tokens or personal details.


def order_placed(
    *,
    order_id: UUID,
    user_id: UUID,
    site_id: UUID,
    side: str,
    energy_kwh: Decimal,
    limit_price_inr_per_kwh: Decimal | None,
    delivery_start: datetime,
    delivery_end: datetime,
    occurred_at: datetime,
) -> AuditEvent:
    return build_event(
        event_type=AuditEventType.ORDER_PLACED,
        entity_id=order_id,
        actor_user_id=user_id,
        occurred_at=occurred_at,
        payload={
            "order_id": order_id,
            "site_id": site_id,
            "side": side,
            "energy_kwh": energy_kwh,
            "limit_price_inr_per_kwh": limit_price_inr_per_kwh,
            "delivery_start": delivery_start,
            "delivery_end": delivery_end,
        },
    )


def market_cleared(
    *,
    market_session_id: UUID,
    market_date: str,
    trade_count: int,
    matched_kwh: Decimal,
    matching_engine: str | None,
    matching_engine_version: str | None,
    occurred_at: datetime,
) -> AuditEvent:
    """Clearing is platform-initiated, so it records no actor."""
    return build_event(
        event_type=AuditEventType.MARKET_CLEARED,
        entity_id=market_session_id,
        occurred_at=occurred_at,
        payload={
            "market_session_id": market_session_id,
            "market_date": market_date,
            "trade_count": trade_count,
            "matched_kwh": matched_kwh,
            "matching_engine": matching_engine,
            "matching_engine_version": matching_engine_version,
        },
    )


def trade_proposed(
    *,
    trade_id: UUID,
    buy_order_id: UUID,
    sell_order_id: UUID,
    quantity_kwh: Decimal,
    clearing_price_inr_per_kwh: Decimal,
    delivery_start: datetime,
    delivery_end: datetime,
    occurred_at: datetime,
) -> AuditEvent:
    return build_event(
        event_type=AuditEventType.TRADE_PROPOSED,
        entity_id=trade_id,
        occurred_at=occurred_at,
        payload={
            "trade_id": trade_id,
            "buy_order_id": buy_order_id,
            "sell_order_id": sell_order_id,
            "quantity_kwh": quantity_kwh,
            "clearing_price_inr_per_kwh": clearing_price_inr_per_kwh,
            "delivery_start": delivery_start,
            "delivery_end": delivery_end,
        },
    )


def grid_validation_recorded(
    *,
    trade_id: UUID,
    grid_validation_id: UUID,
    status: GridValidationStatus,
    decision: str,
    simulation_engine: str,
    engine_version: str | None,
    input_hash: str,
    min_voltage_pu: Decimal | None = None,
    max_voltage_pu: Decimal | None = None,
    max_line_loading_pct: Decimal | None = None,
    max_transformer_loading_pct: Decimal | None = None,
    reason: str | None = None,
    occurred_at: datetime,
) -> AuditEvent:
    """Recorded against the **trade**, with the run id in the payload.

    That is what makes `GET /audit/entities/trade/{id}` return the whole
    lifecycle rather than one event per table.
    """
    return build_event(
        event_type=AuditEventType.GRID_VALIDATION_RECORDED,
        entity_id=trade_id,
        occurred_at=occurred_at,
        payload={
            "trade_id": trade_id,
            "grid_validation_id": grid_validation_id,
            "grid_status": status,
            "decision": decision,
            "simulation_engine": simulation_engine,
            "engine_version": engine_version,
            "input_hash": input_hash,
            "min_voltage_pu": min_voltage_pu,
            "max_voltage_pu": max_voltage_pu,
            "max_line_loading_pct": max_line_loading_pct,
            "max_transformer_loading_pct": max_transformer_loading_pct,
            "reason": reason,
        },
    )


def price_calculated(
    *,
    trade_id: UUID,
    price_components_id: UUID,
    base_market_price: Decimal,
    time_component: Decimal,
    congestion_component: Decimal,
    imbalance_component: Decimal,
    local_renewable_component: Decimal,
    final_price: Decimal,
    formula_version: str,
    occurred_at: datetime,
) -> AuditEvent:
    """Carries the Phase 6 `formula_version`, so a price stays explainable
    after the formula moves on."""
    return build_event(
        event_type=AuditEventType.PRICE_CALCULATED,
        entity_id=trade_id,
        occurred_at=occurred_at,
        payload={
            "trade_id": trade_id,
            "price_components_id": price_components_id,
            "base_market_price": base_market_price,
            "time_component": time_component,
            "congestion_component": congestion_component,
            "imbalance_component": imbalance_component,
            "local_renewable_component": local_renewable_component,
            "final_price": final_price,
            "formula_version": formula_version,
        },
    )


def trade_reconciled(
    *,
    trade_id: UUID,
    reconciliation_id: UUID,
    committed_kwh: Decimal,
    actual_kwh: Decimal | None,
    deviation_kwh: Decimal | None,
    within_tolerance: bool,
    balancing_kwh: Decimal,
    reconciliation_status: str,
    policy_version: str | None = None,
    forecast_basis_id: UUID | None = None,
    occurred_at: datetime,
) -> AuditEvent:
    """`actual_kwh` may be `None`, and is recorded as such.

    An unmeasured window is a fact worth auditing, and writing zero would
    record a shortfall nobody observed.
    """
    return build_event(
        event_type=AuditEventType.TRADE_RECONCILED,
        entity_id=trade_id,
        occurred_at=occurred_at,
        payload={
            "trade_id": trade_id,
            "reconciliation_id": reconciliation_id,
            "committed_kwh": committed_kwh,
            "actual_kwh": actual_kwh,
            "deviation_kwh": deviation_kwh,
            "within_tolerance": within_tolerance,
            "balancing_kwh": balancing_kwh,
            "reconciliation_status": reconciliation_status,
            "policy_version": policy_version,
            "forecast_basis_id": forecast_basis_id,
        },
    )


def trade_settled(
    *,
    trade_id: UUID,
    settlement_id: UUID,
    buyer_user_id: UUID,
    seller_user_id: UUID,
    settled_kwh: Decimal,
    gross_amount_inr: Decimal,
    platform_fee_inr: Decimal,
    balancing_charge_inr: Decimal,
    buyer_debit_inr: Decimal,
    seller_credit_inr: Decimal,
    policy_version: str | None = None,
    price_components_id: UUID | None = None,
    grid_validation_id: UUID | None = None,
    forecast_basis_id: UUID | None = None,
    occurred_at: datetime,
) -> AuditEvent:
    """The event Phase 8 exists for.

    Carries every figure the settlement asserted plus the references that
    justify them, so the settlement can be reconstructed from the audit log
    alone. `policy_version` is accepted and recorded when the caller has one —
    see the Phase 8 handoff for why Phase 7 cannot currently supply it from
    storage.
    """
    return build_event(
        event_type=AuditEventType.TRADE_SETTLED,
        entity_id=trade_id,
        occurred_at=occurred_at,
        payload={
            "trade_id": trade_id,
            "settlement_id": settlement_id,
            "buyer_user_id": buyer_user_id,
            "seller_user_id": seller_user_id,
            "settled_kwh": settled_kwh,
            "gross_amount_inr": gross_amount_inr,
            "platform_fee_inr": platform_fee_inr,
            "balancing_charge_inr": balancing_charge_inr,
            "buyer_debit_inr": buyer_debit_inr,
            "seller_credit_inr": seller_credit_inr,
            "policy_version": policy_version,
            "price_components_id": price_components_id,
            "grid_validation_id": grid_validation_id,
            "forecast_basis_id": forecast_basis_id,
        },
    )


# ---------------------------------------------------------------------------
# Reading and verification
# ---------------------------------------------------------------------------


def timeline(
    session: Session, entity_type: AuditEntityType, entity_id: UUID
) -> list[AuditEventRecord]:
    """One entity's events, oldest first.

    Backs `GET /audit/entities/{entity_type}/{entity_id}`.
    """
    return list(AuditEventRepository(session).list_for_entity(entity_type, entity_id))


def verify(session: Session, *, limit: int | None = None) -> ChainVerification:
    """Walk the stored chain and report whether it is intact.

    Recomputes every hash from the stored content, so it detects an edited
    payload, an edited timestamp, a rewritten hash, and a removed or reordered
    event. Nothing is trusted except the bytes in the table.
    """
    rows = AuditEventRepository(session).list_chain(limit=limit)
    return verify_chain(_rehydrate(row) for row in rows)


def _rehydrate(row: AuditEventRecord) -> SealedAuditEvent:
    """Rebuild the sealed event a row represents.

    The payload comes back exactly as stored, including its own
    `payload_version`, so an event written under an older payload contract is
    verified under that contract rather than today's.
    """
    return SealedAuditEvent(
        event=AuditEvent(
            event_id=row.id,
            event_type=row.event_type,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            event_time=row.event_time,
            recorded_at=row.recorded_at,
            actor_user_id=row.actor_user_id,
            payload=row.payload_json,
        ),
        previous_hash=row.previous_hash,
        event_hash=row.event_hash,
    )


# ---------------------------------------------------------------------------
# Optional ledger anchoring
# ---------------------------------------------------------------------------


def anchor_event(session: Session, event_id: UUID, *, publisher: DLTPublisher) -> AuditEventRecord:
    """Publish one recorded event's evidence and store the reference.

    The single permitted write to an existing audit row, and the reason
    `ledger_anchor_id` is excluded from the hash: the chain must stay valid
    after evidence about it is published.

    Backs `POST /audit/anchor/{entity_type}/{entity_id}`. Anchoring an event
    twice is refused rather than silently re-published, so one event cannot
    accumulate competing references.
    """
    repository = AuditEventRepository(session)
    row = repository.get(event_id)
    if row is None:
        raise NotFoundError(
            "Audit event not found.",
            code="AUDIT_EVENT_NOT_FOUND",
            details={"event_id": str(event_id)},
        )
    if row.ledger_anchor_id is not None:
        raise AuditError(
            "This audit event is already anchored.",
            details={"event_id": str(event_id), "anchor": row.ledger_anchor_id},
        )

    anchor = publisher.publish(_rehydrate(row))
    row.ledger_anchor_id = anchor.reference
    session.commit()
    session.refresh(row)
    return row
