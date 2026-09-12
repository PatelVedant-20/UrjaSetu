"""API contracts for the Users / Identity resource group (docs/05_API_SPEC.md).

Transport-layer models only — no SQL, no business rules
(docs/03_REPOSITORY_STRUCTURE.md ownership rules). Field names and enum values
come from docs/04_DATA_MODEL.md; nothing here is invented.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import UserRole, UserStatus, VerificationLevel

# Deliberately permissive, and deliberately not pydantic's `EmailStr`: that
# would add the `email-validator` dependency, and docs/08_AGENT_GUARDRAILS.md
# requires approval before a new package enters pyproject.toml. The data model
# states no format rule for this column, so this only rejects obvious garbage.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserCreate(BaseModel):
    """`POST /users` request."""

    display_name: str = Field(..., min_length=1, max_length=200)
    role: UserRole
    # Optional: docs/04_DATA_MODEL.md entity 1 makes email nullable so demo
    # auth modes can register an identity without one.
    email: str | None = Field(default=None, max_length=320, pattern=EMAIL_PATTERN)
    status: UserStatus = UserStatus.PENDING


class UserUpdate(BaseModel):
    """`PATCH /users/{user_id}` request — the mutable profile fields.

    `role` is deliberately absent. It determines which side of the market an
    identity may take, so changing it is a re-registration decision rather than
    a profile edit.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320, pattern=EMAIL_PATTERN)
    status: UserStatus | None = None


class UserRead(BaseModel):
    """User profile as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    role: UserRole
    status: UserStatus
    email: str | None
    created_at: datetime
    updated_at: datetime


class EligibilityRead(BaseModel):
    """`GET /users/{user_id}/eligibility` response.

    A direct projection of `app.domain.policies.eligibility.EligibilityDecision`
    — the router does not compute any part of it. `reasons` carries stable
    machine-readable codes so a client can act on them rather than parse prose.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    can_buy: bool
    can_sell: bool
    can_trade: bool
    trust_level: VerificationLevel
    reasons: list[str]
    evaluated_at: datetime
