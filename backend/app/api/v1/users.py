"""Users / Identity endpoints (docs/05_API_SPEC.md).

Transport only: parse, delegate, serialise. No database access and no business
rules — in particular, eligibility is decided entirely by
`app.domain.policies.eligibility` via the identity service.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.users import EligibilityRead, UserCreate, UserRead, UserUpdate
from app.services import identity_service

router = APIRouter(prefix="/users", tags=["users"])

# Shared OpenAPI response documentation. Annotated because FastAPI's
# `responses` parameter is typed as dict[int | str, dict[str, Any]].
NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "User not found"}
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "Email already registered"}
}


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user identity",
    responses=CONFLICT,
)
def create_user(payload: UserCreate, session: DbSession) -> UserRead:
    return UserRead.model_validate(identity_service.create_user(session, payload))


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get user profile",
    responses=NOT_FOUND,
)
def get_user(user_id: UUID, session: DbSession) -> UserRead:
    return UserRead.model_validate(identity_service.get_user(session, user_id))


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Update allowed profile fields",
    responses={**NOT_FOUND, **CONFLICT},
)
def update_user(user_id: UUID, payload: UserUpdate, session: DbSession) -> UserRead:
    return UserRead.model_validate(identity_service.update_user(session, user_id, payload))


@router.get(
    "/{user_id}/eligibility",
    response_model=EligibilityRead,
    summary="Trading eligibility and trust level",
    responses=NOT_FOUND,
)
def get_eligibility(user_id: UUID, session: DbSession) -> EligibilityRead:
    """Return the policy's decision verbatim.

    The router adds no rule of its own; it only attaches the subject and the
    evaluation instant to the decision it was handed.
    """
    decision, evaluated_at = identity_service.get_eligibility(session, user_id)
    return EligibilityRead(
        user_id=user_id,
        can_buy=decision.can_buy,
        can_sell=decision.can_sell,
        can_trade=decision.can_trade,
        trust_level=decision.trust_level,
        reasons=list(decision.reasons),
        evaluated_at=evaluated_at,
    )
