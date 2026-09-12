"""Users and identity endpoints.

Fulfills Phase-1 scope from docs/05_API_SPEC.md:
- POST /users
- GET /users/{user_id}
- PATCH /users/{user_id}
- GET /users/{user_id}/eligibility
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.schemas.users import (
    EligibilityResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services import identity_service

router = APIRouter(tags=["users"])


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create user identity",
)
def create_user(
    payload: UserCreate,
    db: DbSession,
) -> UserResponse:
    """Create a new platform identity (consumer, prosumer, operator, etc.)."""
    user = identity_service.create_user(db, payload)
    return UserResponse.model_validate(user)


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Get user profile",
)
def get_user(
    user_id: uuid.UUID,
    db: DbSession,
) -> UserResponse:
    """Retrieve user profile by unique user ID."""
    user = identity_service.get_user(db, user_id)
    return UserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Update allowed profile fields",
)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: DbSession,
) -> UserResponse:
    """Update mutable user profile fields (e.g. display_name)."""
    user = identity_service.update_user(db, user_id, payload)
    return UserResponse.model_validate(user)


@router.get(
    "/users/{user_id}/eligibility",
    response_model=EligibilityResponse,
    summary="Get trading eligibility and trust level",
)
def get_user_eligibility(
    user_id: uuid.UUID,
    db: DbSession,
) -> EligibilityResponse:
    """Check whether a user is currently eligible to place energy trade orders."""
    return identity_service.get_user_eligibility(db, user_id)
