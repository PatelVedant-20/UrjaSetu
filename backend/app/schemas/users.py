"""User / identity Pydantic schemas.

Transport-layer DTOs only. No persistence logic here
(docs/03_REPOSITORY_STRUCTURE.md ownership rules).

Enum values are validated at this layer so the ORM columns stay plain strings
and a role change in a future phase does not require a DDL migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UserRole(str, Enum):
    consumer = "consumer"
    prosumer = "prosumer"
    operator = "operator"
    regulator_viewer = "regulator_viewer"
    admin = "admin"


class UserStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    pending = "pending"


class VerificationLevel(str, Enum):
    none = "none"
    basic = "basic"
    kyc = "kyc"
    verified = "verified"


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """POST /api/v1/users request body."""

    email: str | None = Field(
        default=None,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Unique email; nullable for demo/anonymous modes.",
        examples=["alice@example.com"],
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable name shown on the platform.",
        examples=["Alice Sharma"],
    )
    role: UserRole = Field(
        default=UserRole.consumer,
        description="Platform role. Determines eligibility and permissions.",
    )


class UserUpdate(BaseModel):
    """PATCH /api/v1/users/{user_id} — only allowed profile fields."""

    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        examples=["Alice Sharma"],
    )
    # Role changes are not permitted via self-service PATCH.
    # Status changes require operator action (future phase).


class UserResponse(BaseModel):
    """User resource representation returned by all user endpoints."""

    id: uuid.UUID
    email: str | None
    display_name: str
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EligibilityResponse(BaseModel):
    """GET /api/v1/users/{user_id}/eligibility."""

    user_id: uuid.UUID
    eligible_to_trade: bool
    role: UserRole
    status: UserStatus
    # verification_level of the highest-ranked utility account or "none"
    verification_level: VerificationLevel
    reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable reasons when eligibility is false.",
    )


# ---------------------------------------------------------------------------
# Utility account schemas (nested in user responses / separate create)
# ---------------------------------------------------------------------------


class UtilityAccountCreate(BaseModel):
    """Embedded in user creation or as a standalone sub-resource (Phase 2+)."""

    discom_code: str = Field(
        ...,
        max_length=64,
        description="DISCOM identifier code (e.g. MSEDCL, BESCOM).",
        examples=["MSEDCL"],
    )
    # Application layer hashes this before persistence.
    # Raw consumer numbers must never be stored (docs/00_PROJECT_BIBLE.md §8).
    consumer_number_raw: str | None = Field(
        default=None,
        description=(
            "Raw consumer number — hashed before storage. "
            "Never persisted in plaintext."
        ),
        examples=["1234567890"],
    )


class UtilityAccountResponse(BaseModel):
    """Utility account representation — never exposes raw consumer number."""

    id: uuid.UUID
    user_id: uuid.UUID
    discom_code: str
    # Only the hash is returned; the raw value is never surfaced.
    consumer_number_hash: str | None
    verification_level: VerificationLevel
    verified_at: datetime | None

    model_config = {"from_attributes": True}
