"""Audit API endpoints (docs/05_API_SPEC.md).

Transport only: parse, validate access control, delegate to
`app.services.audit_service`, serialize responses.
No hashing or verification math in routes.
Audit logs are protected and not world-readable.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.adapters.ledger.local_publisher import LocalFilePublisher
from app.api.deps import CurrentUser, DbSession
from app.core.errors import ForbiddenError, NotFoundError
from app.db.models.audit import AuditEventRecord
from app.db.models.market import Order, Trade
from app.domain.enums import AuditEntityType, UserRole
from app.schemas.audit import AuditEventRead
from app.schemas.common import ErrorResponse
from app.services import audit_service

router = APIRouter(tags=["audit"])

UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication required"}
}
FORBIDDEN: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "Access denied"}
}
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Entity or audit event not found"}
}
UNPROCESSABLE: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Operation invalid or already anchored"}
}

COMMON_RESPONSES = {**UNAUTHORIZED, **FORBIDDEN, **NOT_FOUND}


def _verify_timeline_access(
    session: DbSession,
    user: CurrentUser,
    entity_type: AuditEntityType,
    entity_id: UUID,
) -> None:
    """Enforce authorization policy for audit timeline reads.

    - ADMIN, OPERATOR, REGULATOR_VIEWER: full read access across all entities.
    - CONSUMER, PROSUMER: permitted only if directly participating in the entity.
    """
    if user.role in (UserRole.ADMIN, UserRole.OPERATOR, UserRole.REGULATOR_VIEWER):
        return

    if entity_type is AuditEntityType.ORDER:
        order = session.get(Order, entity_id)
        if order is not None and order.user_id != user.id:
            raise ForbiddenError(
                "You are not authorized to view the audit timeline for this order.",
                details={"entity_id": str(entity_id), "user_id": str(user.id)},
            )
        return

    if entity_type is AuditEntityType.TRADE:
        trade = session.get(Trade, entity_id)
        if trade is not None:
            buy_order = session.get(Order, trade.buy_order_id)
            sell_order = session.get(Order, trade.sell_order_id)
            participants = {
                buy_order.user_id if buy_order else None,
                sell_order.user_id if sell_order else None,
            }
            if user.id not in participants:
                raise ForbiddenError(
                    "You are not authorized to view the audit timeline for this trade.",
                    details={"entity_id": str(entity_id), "user_id": str(user.id)},
                )
        return

    # Market sessions are administrative and not visible to retail participants
    raise ForbiddenError(
        "Participant roles cannot view market session audit timelines.",
        details={"entity_type": entity_type.value, "role": user.role.value},
    )


@router.get(
    "/audit/entities/{entity_type}/{entity_id}",
    response_model=list[AuditEventRead],
    summary="Timeline of material business events for an entity",
    responses=COMMON_RESPONSES,
)
def get_audit_timeline(
    entity_type: AuditEntityType,
    entity_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> list[AuditEventRead]:
    """Return an entity's complete chronological audit event timeline.

    Protected: requires authenticated identity and appropriate role/participation access.
    """
    _verify_timeline_access(session, current_user, entity_type, entity_id)
    events = audit_service.timeline(session, entity_type, entity_id)
    return [AuditEventRead.model_validate(event) for event in events]


@router.post(
    "/audit/anchor/{entity_type}/{entity_id}",
    response_model=AuditEventRead,
    status_code=status.HTTP_200_OK,
    summary="Anchor a finalized audit event hash to the configured ledger adapter",
    responses={**COMMON_RESPONSES, **UNPROCESSABLE},
)
def anchor_audit_event(
    entity_type: AuditEntityType,
    entity_id: UUID,
    current_user: CurrentUser,
    session: DbSession,
) -> AuditEventRead:
    """Anchor an audit event to the external ledger adapter and record proof.

    Restricted to ADMIN and OPERATOR roles only.
    Resolves event ID directly or selects the latest event for the target entity.
    """
    if current_user.role not in (UserRole.ADMIN, UserRole.OPERATOR):
        raise ForbiddenError(
            "Only administrators and operators are authorized to anchor audit events.",
            details={"role": current_user.role.value},
        )

    # 1. Check if entity_id is already an AuditEventRecord id
    target_event = session.get(AuditEventRecord, entity_id)

    # 2. Otherwise resolve latest event for the given entity
    if target_event is None:
        events = audit_service.timeline(session, entity_type, entity_id)
        if not events:
            raise NotFoundError(
                "No audit events found for entity to anchor.",
                code="AUDIT_EVENT_NOT_FOUND",
                details={"entity_type": entity_type.value, "entity_id": str(entity_id)},
            )
        # Prefer latest unanchored event
        unanchored = [e for e in events if e.ledger_anchor_id is None]
        target_event = unanchored[-1] if unanchored else events[-1]

    publisher = LocalFilePublisher()
    anchored = audit_service.anchor_event(session, target_event.id, publisher=publisher)
    return AuditEventRead.model_validate(anchored)
