"""Phase 7 verification: reconciliation, accounting and transaction semantics.

The properties that matter: the four quantities stay distinct, an unmeasured
window never becomes a measured zero, settlement pays the *effective* Phase 6
price rather than the Phase 4 clearing price, and the ledger balances exactly.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import ReconciliationStatus, SettlementStatus
from app.repositories.settlement import MeterReconciliationRepository, SettlementRepository
from app.services import pricing_service, settlement_service
from app.services.settlement_service import NotReconcilableError

from .conftest import CLEARING_PRICE, COMMITTED_KWH, Lifecycle


def _price(db_session: Session, lifecycle: Lifecycle) -> Decimal:
    """Run Phase 6 so an effective price exists, and return it."""
    return pricing_service.price_trade(db_session, lifecycle.trade.id).final_price


# ---------------------------------------------------------------------------
# The effective price is the settlement price
# ---------------------------------------------------------------------------


def test_settlement_pays_the_effective_price_not_the_clearing_price(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """The Phase 6 -> Phase 7 link, checked on the money rather than on types."""
    effective = _price(db_session, lifecycle)
    assert effective != CLEARING_PRICE, "the fixture must exercise a price that actually moved"

    deliver(COMMITTED_KWH)
    settlement = settlement_service.settle_trade(db_session, lifecycle.trade.id)

    assert settlement.gross_amount_inr == (COMMITTED_KWH * effective).quantize(Decimal("0.01"))
    assert settlement.gross_amount_inr != (COMMITTED_KWH * CLEARING_PRICE).quantize(Decimal("0.01"))


def test_settlement_without_a_price_is_refused_rather_than_guessed(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """No breakdown means no price. It must not fall back to the clearing price."""
    deliver(COMMITTED_KWH)

    with pytest.raises(Exception) as caught:
        settlement_service.settle_trade(db_session, lifecycle.trade.id)

    assert "PRICE_BREAKDOWN_NOT_FOUND" in str(getattr(caught.value, "code", caught.value))


# ---------------------------------------------------------------------------
# Measured zero is not missing telemetry
# ---------------------------------------------------------------------------


def test_missing_telemetry_refuses_to_settle(db_session: Session, lifecycle: Lifecycle) -> None:
    """No usable reading at all: awaiting telemetry, and no settlement row."""
    _price(db_session, lifecycle)

    with pytest.raises(NotReconcilableError):
        settlement_service.settle_trade(db_session, lifecycle.trade.id)

    reconciliation = MeterReconciliationRepository(db_session).latest_for_trade(lifecycle.trade.id)
    assert reconciliation is not None
    assert reconciliation.reconciliation_status is ReconciliationStatus.AWAITING_TELEMETRY
    assert reconciliation.actual_kwh is None, "unmeasured must never be stored as zero"
    assert SettlementRepository(db_session).active_for_trade(lifecycle.trade.id) is None


def test_measured_zero_settles_as_a_total_shortfall(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """A meter that reported zero is an observation, and is settled as one."""
    _price(db_session, lifecycle)
    deliver(Decimal("0"))

    settlement = settlement_service.settle_trade(db_session, lifecycle.trade.id)
    reconciliation = MeterReconciliationRepository(db_session).latest_for_trade(lifecycle.trade.id)

    assert reconciliation is not None
    assert reconciliation.actual_kwh == Decimal("0")
    assert reconciliation.reconciliation_status is ReconciliationStatus.RECONCILED
    assert settlement.settled_kwh == Decimal("0")
    assert settlement.balancing_charge_inr > Decimal("0")


def test_energy_with_no_reading_is_not_the_same_as_a_zero_reading(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """A reading carrying no energy value leaves the window unmeasured."""
    _price(db_session, lifecycle)
    deliver(None)

    with pytest.raises(NotReconcilableError):
        settlement_service.settle_trade(db_session, lifecycle.trade.id)


# ---------------------------------------------------------------------------
# Quantities and accounting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("delivered", "expect_within_tolerance", "expect_balancing"),
    [
        (Decimal("10.0"), True, False),
        (Decimal("9.7"), True, False),
        (Decimal("8.0"), False, True),
        (Decimal("12.0"), False, False),
    ],
    ids=["exact", "small_shortfall", "breach", "over_delivery"],
)
def test_committed_actual_and_settled_stay_distinct(
    db_session: Session,
    lifecycle: Lifecycle,
    deliver: Callable[[Decimal | None], None],
    delivered: Decimal,
    expect_within_tolerance: bool,
    expect_balancing: bool,
) -> None:
    _price(db_session, lifecycle)
    deliver(delivered)

    settlement = settlement_service.settle_trade(db_session, lifecycle.trade.id)
    reconciliation = MeterReconciliationRepository(db_session).latest_for_trade(lifecycle.trade.id)
    assert reconciliation is not None

    assert reconciliation.committed_kwh == COMMITTED_KWH
    assert reconciliation.actual_kwh == delivered
    assert settlement.settled_kwh == min(COMMITTED_KWH, delivered)
    assert reconciliation.within_tolerance is expect_within_tolerance
    assert (reconciliation.balancing_kwh > Decimal("0")) is expect_balancing
    # Over-delivery is never balanced: the surplus was simply not traded.
    if delivered > COMMITTED_KWH:
        assert reconciliation.balancing_kwh == Decimal("0")


def test_the_ledger_balances_exactly(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """buyer debit = seller credit + platform fee + balancing charge."""
    _price(db_session, lifecycle)
    deliver(Decimal("8.0"))

    s = settlement_service.settle_trade(db_session, lifecycle.trade.id)

    assert s.buyer_debit_inr == s.seller_credit_inr + s.platform_fee_inr + s.balancing_charge_inr
    assert s.gross_amount_inr.as_tuple().exponent == -2, "money is settled to the paise"


def test_resettlement_supersedes_rather_than_overwrites(
    db_session: Session, lifecycle: Lifecycle, deliver: Callable[[Decimal | None], None]
) -> None:
    """Financial history is appended to, never destroyed."""
    _price(db_session, lifecycle)
    deliver(Decimal("10.0"))

    first = settlement_service.settle_trade(db_session, lifecycle.trade.id)
    second = settlement_service.settle_trade(db_session, lifecycle.trade.id)

    db_session.refresh(first)
    assert first.status is SettlementStatus.SUPERSEDED
    assert second.status is SettlementStatus.SETTLED
    assert len(SettlementRepository(db_session).list_for_trade(lifecycle.trade.id)) == 2
    assert (
        settlement_service.active_settlement_for_trade(db_session, lifecycle.trade.id).id
        == second.id
    )
