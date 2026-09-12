"""Trading-eligibility policy.

Answers `GET /users/{user_id}/eligibility` (docs/05_API_SPEC.md) and closes the
Phase 1 gate in docs/07_CODING_PHASES.md:

    create user -> create site -> attach meter -> add PV -> verify -> eligibility

Pure and deterministic: every function here takes plain values and returns
plain values. No database access, no ORM types, no clock reads — `evaluated_at`
is always passed in. That is what makes the decision reproducible and
explainable from stored inputs (docs/00_PROJECT_BIBLE.md: traceability), and
what lets it be tested without PostgreSQL.

The rules encode docs/11_REGULATORY_AND_INDIA_CONTEXT.md: DISCOM verification
and meter verification precede trading, and settlement is bill-based, so the
DISCOM link is mandatory on both sides of the market.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import (
    UserRole,
    UserStatus,
    VerificationLevel,
    VerificationStatus,
)

# Roles that may transact at all. Operators and regulator viewers observe the
# market; they never take a position in it.
TRADING_ROLES: frozenset[UserRole] = frozenset({UserRole.CONSUMER, UserRole.PROSUMER})

# Only a prosumer sells: selling requires owned generation.
SELLING_ROLES: frozenset[UserRole] = frozenset({UserRole.PROSUMER})

# The DISCOM must have confirmed the connection before money moves through a
# utility bill.
MINIMUM_TRADING_LEVEL = VerificationLevel.DISCOM_VERIFIED


@dataclass(frozen=True)
class VerificationEvidence:
    """One verification record, reduced to what the policy needs.

    Deliberately not the ORM model: the policy must not depend on persistence.
    """

    status: VerificationStatus
    level: VerificationLevel
    expires_at: datetime | None = None


@dataclass(frozen=True)
class EligibilityInput:
    """Everything the decision depends on, resolved by the caller."""

    role: UserRole
    status: UserStatus
    evaluated_at: datetime
    utility_account_level: VerificationLevel = VerificationLevel.NONE
    meter_level: VerificationLevel = VerificationLevel.NONE
    has_market_participation_consent: bool = False
    has_meter_data_consent: bool = False
    has_active_generation_asset: bool = False


@dataclass(frozen=True)
class EligibilityDecision:
    """The answer, with every reason it came out that way.

    `reasons` holds stable machine-readable codes rather than prose so the API
    layer and the UI can both act on them.
    """

    can_buy: bool
    can_sell: bool
    trust_level: VerificationLevel
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def can_trade(self) -> bool:
        return self.can_buy or self.can_sell


def resolve_verification_level(
    evidence: Iterable[VerificationEvidence],
    *,
    at: datetime,
) -> VerificationLevel:
    """The highest level actually in force at `at`.

    A record counts only while its status is VERIFIED and it has not expired.
    An expired record is silently ignored rather than treated as its stored
    level — that stored level is history, not current trust.

    Returns `NONE` when nothing qualifies.
    """
    best = VerificationLevel.NONE
    for item in evidence:
        if item.status is not VerificationStatus.VERIFIED:
            continue
        if item.expires_at is not None and item.expires_at <= at:
            continue
        if item.level.rank > best.rank:
            best = item.level
    return best


def evaluate_eligibility(data: EligibilityInput) -> EligibilityDecision:
    """Decide whether a user may buy and/or sell.

    Buying and selling are evaluated separately because a consumer with a
    verified connection can buy long before they own any generation.
    """
    blocking: list[str] = []

    if data.status is not UserStatus.ACTIVE:
        blocking.append("USER_NOT_ACTIVE")
    if data.role not in TRADING_ROLES:
        blocking.append("ROLE_NOT_PERMITTED_TO_TRADE")
    if data.utility_account_level.rank < MINIMUM_TRADING_LEVEL.rank:
        blocking.append("UTILITY_ACCOUNT_NOT_DISCOM_VERIFIED")
    if not data.has_market_participation_consent:
        blocking.append("MARKET_PARTICIPATION_CONSENT_MISSING")

    can_buy = not blocking

    # Selling adds the obligations that come with injecting energy: owned
    # generation, a verified meter to measure it, and consent to read that
    # meter for reconciliation.
    sell_blocking = list(blocking)
    if data.role not in SELLING_ROLES:
        sell_blocking.append("ROLE_NOT_PERMITTED_TO_SELL")
    if not data.has_active_generation_asset:
        sell_blocking.append("NO_ACTIVE_GENERATION_ASSET")
    if data.meter_level.rank < MINIMUM_TRADING_LEVEL.rank:
        sell_blocking.append("METER_NOT_DISCOM_VERIFIED")
    if not data.has_meter_data_consent:
        sell_blocking.append("METER_DATA_CONSENT_MISSING")

    can_sell = not sell_blocking

    # Trust is the weaker of the two links: an unverified meter cannot be
    # compensated for by a verified utility account.
    trust_level = min(
        data.utility_account_level,
        data.meter_level,
        key=lambda level: level.rank,
    )

    # Deduplicated, order preserved, so the payload is stable for a given input.
    reasons = tuple(dict.fromkeys(sell_blocking))

    return EligibilityDecision(
        can_buy=can_buy,
        can_sell=can_sell,
        trust_level=trust_level,
        reasons=reasons,
    )
