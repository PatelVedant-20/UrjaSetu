"""Settlement API endpoints (docs/05_API_SPEC.md).

Transport only: parse, validate parameters, delegate to
`app.services.settlement_service`, serialise responses.
No SQL, no business logic, no deviation/tolerance math, and no fee/accounting
calculations in routers.
The settlement service and calculator remain the sole owners of settlement behavior.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.settlement import MeterReconciliationRead, SettlementRead
from app.services import identity_service, settlement_service

router = APIRouter(tags=["settlement"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"}
}
UNPROCESSABLE: dict[int | str, dict[str, Any]] = {
    422: {
        "model": ErrorResponse,
        "description": "Settlement not reconcilable or calculation failed",
    }
}


@router.post(
    "/trades/{trade_id}/reconcile",
    response_model=MeterReconciliationRead,
    status_code=status.HTTP_200_OK,
    summary="Compare actual delivery vs committed energy for a trade",
    responses={**NOT_FOUND, **UNPROCESSABLE},
)
def reconcile_trade(
    trade_id: UUID,
    session: DbSession,
) -> MeterReconciliationRead:
    """Compare actual meter delivery against trade commitment and record the outcome.

    Delegates entirely to SettlementService. Always produces a reconciliation
    record, even if telemetry is missing/unmeasured.
    """
    reconciliation = settlement_service.reconcile_trade(session, trade_id)
    return MeterReconciliationRead.model_validate(reconciliation)


@router.post(
    "/trades/{trade_id}/settle",
    response_model=SettlementRead,
    status_code=status.HTTP_200_OK,
    summary="Create final settlement after reconciliation rules are satisfied",
    responses={**NOT_FOUND, **UNPROCESSABLE},
)
def settle_trade(
    trade_id: UUID,
    session: DbSession,
) -> SettlementRead:
    """Perform financial allocation and record final settlement for a completed trade.

    Refuses trades whose delivery has not yet been measured (raises 422
    SETTLEMENT_NOT_RECONCILABLE). Enforces ledger balance invariants.
    """
    settlement = settlement_service.settle_trade(session, trade_id)
    return SettlementRead.model_validate(settlement)


@router.get(
    "/settlements/{settlement_id}",
    response_model=SettlementRead,
    summary="Get settlement result by ID",
    responses=NOT_FOUND,
)
def get_settlement(
    settlement_id: UUID,
    session: DbSession,
) -> SettlementRead:
    """Fetch stored settlement record by unique ID."""
    settlement = settlement_service.get_settlement(session, settlement_id)
    return SettlementRead.model_validate(settlement)


@router.get(
    "/users/{user_id}/settlements",
    response_model=list[SettlementRead],
    summary="Get settlement history for a user",
    responses=NOT_FOUND,
)
def list_user_settlements(
    user_id: UUID,
    session: DbSession,
) -> list[SettlementRead]:
    """Fetch all settlements where the user is either buyer or seller, newest first."""
    # Ensure user exists before listing settlements
    identity_service.get_user(session, user_id)
    settlements = settlement_service.list_settlements_for_user(session, user_id)
    return [SettlementRead.model_validate(s) for s in settlements]
