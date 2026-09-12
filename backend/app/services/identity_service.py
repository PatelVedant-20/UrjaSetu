"""Identity service for user management and trading eligibility.

Coordinates database persistence and queries for the User and UtilityAccount
domain models (docs/03_REPOSITORY_STRUCTURE.md, docs/05_API_SPEC.md).
"""Identity service — users and trading eligibility.

Owns the transaction boundary for identity writes (docs/04_DATA_MODEL.md,
"Transaction Boundaries").

It contains no eligibility rules of its own. For
`GET /users/{user_id}/eligibility` its only job is to *gather evidence* and
hand it to `app.domain.policies.eligibility`, which is the single place the
decision is made.
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
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User, VerificationRecord
from app.domain.enums import (
    ConsentScope,
    EnergyAssetStatus,
    EnergyAssetType,
    VerificationLevel,
    VerificationType,
)
from app.domain.policies import (
    EligibilityDecision,
    EligibilityInput,
    VerificationEvidence,
    evaluate_eligibility,
    resolve_verification_level,
)
from app.repositories import (
    ConsentRepository,
    EnergyAssetRepository,
    MeterRepository,
    SiteRepository,
    UserRepository,
    UtilityAccountRepository,
    VerificationRecordRepository,
)
from app.schemas.users import UserCreate, UserUpdate
from app.services import ResourceConflictError, ResourceNotFoundError

# Asset types that can inject energy into the grid. Batteries count because
# they discharge; EV is load-side in Phase 1.
GENERATION_ASSET_TYPES = frozenset({EnergyAssetType.PV, EnergyAssetType.BATTERY})

# Which evidence raises which trust link. Identity evidence supports the
# utility-account link because both attest "this person holds this connection"
# (docs/11_REGULATORY_AND_INDIA_CONTEXT.md: verified credential).
UTILITY_EVIDENCE_TYPES = frozenset({VerificationType.UTILITY_ACCOUNT, VerificationType.IDENTITY})
METER_EVIDENCE_TYPES = frozenset({VerificationType.METER})


def create_user(session: Session, payload: UserCreate) -> User:
    """Create an identity. One transaction."""
    repo = UserRepository(session)

    if payload.email is not None and repo.get_by_email(payload.email) is not None:
        raise ResourceConflictError(
            "A user with this email already exists.",
            code="USER_EMAIL_ALREADY_EXISTS",
            details={"email": payload.email},
        )

    user = User(
        display_name=payload.display_name,
        role=payload.role,
        status=payload.status,
        email=payload.email,
    )
    try:
        repo.add(user)
        session.commit()
    except IntegrityError as exc:
        # The lookup above narrows the race window; the unique index closes it.
        session.rollback()
        raise ResourceConflictError(
            "A user with this email already exists.",
            code="USER_EMAIL_ALREADY_EXISTS",
        ) from exc

    session.refresh(user)
    return user


def get_user(session: Session, user_id: UUID) -> User:
    user = UserRepository(session).get(user_id)
    if user is None:
        raise ResourceNotFoundError("user", user_id)
    return user


def update_user(session: Session, user_id: UUID, payload: UserUpdate) -> User:
    """Apply a partial profile update. Unset fields are left untouched."""
    user = get_user(session, user_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    try:
        session.flush()
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ResourceConflictError(
            "A user with this email already exists.",
            code="USER_EMAIL_ALREADY_EXISTS",
        ) from exc

    session.refresh(user)
    return user


def get_eligibility(
    session: Session, user_id: UUID, *, at: datetime | None = None
) -> tuple[EligibilityDecision, datetime]:
    """Evaluate trading eligibility for a user.

    Gathers evidence, then delegates every rule to the pure policy. The
    evaluation instant is captured once and passed in, so the result is
    reproducible from stored inputs (docs/00_PROJECT_BIBLE.md: traceability).
    """
    user = get_user(session, user_id)
    evaluated_at = at or datetime.now(UTC)

    records = VerificationRecordRepository(session).list_for_user(user_id)
    consents = ConsentRepository(session)

    decision = evaluate_eligibility(
        EligibilityInput(
            role=user.role,
            status=user.status,
            evaluated_at=evaluated_at,
            utility_account_level=_utility_account_level(
                session,
                user_id,
                _level_from_records(records, UTILITY_EVIDENCE_TYPES, at=evaluated_at),
            ),
            meter_level=_meter_level(
                session,
                user_id,
                _level_from_records(records, METER_EVIDENCE_TYPES, at=evaluated_at),
            ),
            has_market_participation_consent=consents.has_active_scope(
                user_id, ConsentScope.MARKET_PARTICIPATION
            ),
            has_meter_data_consent=consents.has_active_scope(user_id, ConsentScope.METER_DATA),
            has_active_generation_asset=_has_active_generation_asset(session, user_id),
        )
    )
    return decision, evaluated_at


def _level_from_records(
    records: Sequence[VerificationRecord],
    types: Collection[VerificationType],
    *,
    at: datetime,
) -> VerificationLevel:
    """Highest in-force level among records of the given types.

    Status and expiry are judged by the policy, not here.
    """
    return resolve_verification_level(
        (
            VerificationEvidence(
                status=record.status,
                level=record.verification_level,
                expires_at=record.expires_at,
            )
            for record in records
            if record.verification_type in types
        ),
        at=at,
    )


def _strongest(*levels: VerificationLevel) -> VerificationLevel:
    return max(levels, key=lambda level: level.rank)


def _utility_account_level(
    session: Session, user_id: UUID, from_records: VerificationLevel
) -> VerificationLevel:
    """Trust in the user's DISCOM connection.

    Two sources: the level stored on `utility_accounts`, and verification
    records attesting the connection. The stronger wins — either is sufficient
    evidence on its own.
    """
    accounts = UtilityAccountRepository(session).list_for_user(user_id)
    stored = [a.verification_level for a in accounts if a.verified_at is not None]
    return _strongest(*stored, from_records)


def _meter_level(
    session: Session, user_id: UUID, from_records: VerificationLevel
) -> VerificationLevel:
    """Trust in the user's metering, across every site they own.

    Inactive meters are ignored: a decommissioned meter cannot measure a trade.
    """
    meter_repo = MeterRepository(session)
    stored = [
        meter.verification_level
        for site in SiteRepository(session).list_for_owner(user_id)
        for meter in meter_repo.list_for_site(site.id)
        if meter.active
    ]
    return _strongest(*stored, from_records)


def _has_active_generation_asset(session: Session, user_id: UUID) -> bool:
    """Whether the user owns anything that can inject energy, right now."""
    return any(
        asset.asset_type in GENERATION_ASSET_TYPES and asset.status is EnergyAssetStatus.ACTIVE
        for asset in EnergyAssetRepository(session).list_for_owner(user_id)
    )
