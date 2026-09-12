"""Phase 1: trading-eligibility policy — core paths only.

Deliberately narrow. docs/07_CODING_PHASES.md assigns the validation and
edge-case suite for this logic to Vedant; this file covers the happy path, the
main denials and the determinism guarantee, so the policy has a contract to
build those tests against.

No database and no clock: the policy is pure, so these are true unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.enums import (
    UserRole,
    UserStatus,
    VerificationLevel,
    VerificationStatus,
)
from app.domain.policies import (
    EligibilityInput,
    VerificationEvidence,
    evaluate_eligibility,
    resolve_verification_level,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _verified_prosumer(**overrides: object) -> EligibilityInput:
    """A prosumer who satisfies every requirement, before overrides."""
    defaults: dict[str, object] = {
        "role": UserRole.PROSUMER,
        "status": UserStatus.ACTIVE,
        "evaluated_at": NOW,
        "utility_account_level": VerificationLevel.DISCOM_VERIFIED,
        "meter_level": VerificationLevel.DISCOM_VERIFIED,
        "has_market_participation_consent": True,
        "has_meter_data_consent": True,
        "has_active_generation_asset": True,
    }
    return EligibilityInput(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_fully_verified_prosumer_can_buy_and_sell() -> None:
    decision = evaluate_eligibility(_verified_prosumer())

    assert decision.can_buy is True
    assert decision.can_sell is True
    assert decision.trust_level is VerificationLevel.DISCOM_VERIFIED
    assert decision.reasons == ()


def test_verified_consumer_can_buy_but_not_sell() -> None:
    decision = evaluate_eligibility(
        _verified_prosumer(role=UserRole.CONSUMER, has_active_generation_asset=False)
    )

    assert decision.can_buy is True
    assert decision.can_sell is False
    assert "ROLE_NOT_PERMITTED_TO_SELL" in decision.reasons


def test_unverified_utility_account_blocks_all_trading() -> None:
    """Settlement is bill-based, so the DISCOM link is mandatory on both sides."""
    decision = evaluate_eligibility(
        _verified_prosumer(utility_account_level=VerificationLevel.SELF_DECLARED)
    )

    assert decision.can_buy is False
    assert decision.can_sell is False
    assert "UTILITY_ACCOUNT_NOT_DISCOM_VERIFIED" in decision.reasons


def test_unverified_meter_blocks_selling_only() -> None:
    decision = evaluate_eligibility(
        _verified_prosumer(meter_level=VerificationLevel.DOCUMENT_VERIFIED)
    )

    assert decision.can_buy is True
    assert decision.can_sell is False
    assert "METER_NOT_DISCOM_VERIFIED" in decision.reasons


def test_suspended_user_cannot_trade() -> None:
    decision = evaluate_eligibility(_verified_prosumer(status=UserStatus.SUSPENDED))

    assert decision.can_trade is False
    assert "USER_NOT_ACTIVE" in decision.reasons


def test_observer_roles_cannot_trade() -> None:
    for role in (UserRole.OPERATOR, UserRole.REGULATOR_VIEWER, UserRole.ADMIN):
        decision = evaluate_eligibility(_verified_prosumer(role=role))
        assert decision.can_trade is False, role
        assert "ROLE_NOT_PERMITTED_TO_TRADE" in decision.reasons


def test_missing_generation_asset_blocks_selling() -> None:
    decision = evaluate_eligibility(_verified_prosumer(has_active_generation_asset=False))

    assert decision.can_buy is True
    assert decision.can_sell is False
    assert "NO_ACTIVE_GENERATION_ASSET" in decision.reasons


def test_trust_level_is_the_weaker_of_the_two_links() -> None:
    decision = evaluate_eligibility(_verified_prosumer(meter_level=VerificationLevel.NONE))

    assert decision.trust_level is VerificationLevel.NONE


def test_decision_is_deterministic() -> None:
    """Same input, same output — required by docs/10_TESTING_AND_INTEGRATION.md."""
    data = _verified_prosumer(status=UserStatus.PENDING, meter_level=VerificationLevel.NONE)

    assert evaluate_eligibility(data) == evaluate_eligibility(data)


def test_resolve_verification_level_takes_the_highest_in_force() -> None:
    level = resolve_verification_level(
        [
            VerificationEvidence(VerificationStatus.VERIFIED, VerificationLevel.SELF_DECLARED),
            VerificationEvidence(VerificationStatus.VERIFIED, VerificationLevel.DISCOM_VERIFIED),
        ],
        at=NOW,
    )

    assert level is VerificationLevel.DISCOM_VERIFIED


def test_resolve_verification_level_ignores_expired_evidence() -> None:
    """An expired record is history, not current trust."""
    level = resolve_verification_level(
        [
            VerificationEvidence(
                VerificationStatus.VERIFIED,
                VerificationLevel.DISCOM_VERIFIED,
                expires_at=NOW - timedelta(days=1),
            ),
            VerificationEvidence(VerificationStatus.VERIFIED, VerificationLevel.SELF_DECLARED),
        ],
        at=NOW,
    )

    assert level is VerificationLevel.SELF_DECLARED


def test_resolve_verification_level_ignores_unverified_evidence() -> None:
    level = resolve_verification_level(
        [
            VerificationEvidence(VerificationStatus.PENDING, VerificationLevel.DISCOM_VERIFIED),
            VerificationEvidence(VerificationStatus.REJECTED, VerificationLevel.DISCOM_VERIFIED),
            VerificationEvidence(VerificationStatus.REVOKED, VerificationLevel.DISCOM_VERIFIED),
        ],
        at=NOW,
    )

    assert level is VerificationLevel.NONE


def test_resolve_verification_level_with_no_evidence_is_none() -> None:
    assert resolve_verification_level([], at=NOW) is VerificationLevel.NONE
