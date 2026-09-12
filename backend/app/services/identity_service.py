"""Identity service for user management and trading eligibility.

Coordinates database persistence and queries for the User and UtilityAccount
domain models (docs/03_REPOSITORY_STRUCTURE.md, docs/05_API_SPEC.md).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models.identity import User
from app.schemas.users import (
    EligibilityResponse,
    UserCreate,
    UserRole,
    UserStatus,
    UserUpdate,
    VerificationLevel,
)


def create_user(db: Session, payload: UserCreate) -> User:
    """Create a new platform identity."""
    if payload.email:
        existing = db.execute(
            select(User).where(User.email == payload.email)
        ).scalar_one_or_none()
        if existing:
            raise ConflictError(
                f"User with email '{payload.email}' already exists.",
                details={"email": payload.email},
            )

    user = User(
        email=payload.email,
        display_name=payload.display_name,
        role=payload.role.value,
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: uuid.UUID) -> User:
    """Retrieve user by ID or raise NotFoundError."""
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError(
            f"User with id '{user_id}' was not found.",
            details={"user_id": str(user_id)},
        )
    return user


def update_user(db: Session, user_id: uuid.UUID, payload: UserUpdate) -> User:
    """Update allowed profile fields (display_name)."""
    user = get_user(db, user_id)

    if payload.display_name is not None:
        user.display_name = payload.display_name

    db.commit()
    db.refresh(user)
    return user


def get_user_eligibility(db: Session, user_id: uuid.UUID) -> EligibilityResponse:
    """Evaluate trading eligibility and trust level for a user."""
    user = get_user(db, user_id)

    reasons: list[str] = []
    is_eligible = True

    # Check status
    if user.status != "active":
        is_eligible = False
        reasons.append(f"Account status is '{user.status}', not active.")

    # Check role
    allowed_roles = {"consumer", "prosumer"}
    if user.role not in allowed_roles:
        is_eligible = False
        reasons.append(
            f"Role '{user.role}' is not eligible for peer-to-peer trading. "
            "Must be 'consumer' or 'prosumer'."
        )

    # Determine highest verification level from utility accounts
    # Rank order: verified > kyc > basic > none
    rank = {"verified": 3, "kyc": 2, "basic": 1, "none": 0}
    highest_level = "none"

    for ua in user.utility_accounts:
        if rank.get(ua.verification_level, 0) > rank.get(highest_level, 0):
            highest_level = ua.verification_level

    # Check verification level: if "none" and no utility account, note reason
    if not user.utility_accounts:
        # For Phase 1 demo, consumer/prosumer without utility account is eligible with basic trust
        # unless suspended
        pass

    try:
        v_level = VerificationLevel(highest_level)
    except ValueError:
        v_level = VerificationLevel.none

    return EligibilityResponse(
        user_id=user.id,
        eligible_to_trade=is_eligible,
        role=UserRole(user.role),
        status=UserStatus(user.status),
        verification_level=v_level,
        reasons=reasons,
    )
