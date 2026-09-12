"""Phase 4 fixtures.

The engines here are **stand-ins for the contract, not matching algorithms**.
The real engine lives in `app/domain/policies/market_matching.py` and is owned
by the agent assigned that module; these exist only to prove the orchestration
layer can drive anything satisfying `MatchingEngine`, including one that
misbehaves.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.db.models import Consent, EnergyAsset, Meter, Site, User
from app.domain.enums import (
    ConsentScope,
    EnergyAssetStatus,
    OrderSide,
    UserRole,
    UserStatus,
    VerificationLevel,
    VerificationSource,
    VerificationStatus,
    VerificationType,
)
from app.domain.interfaces.market import (
    MatchingRequest,
    MatchingResult,
    ProposedTrade,
)
from app.domain.policies.clearing_price import midpoint_clearing_price, prices_cross

# Re-exported so Phase 4 tests can build the registry an order hangs off
# (user -> site -> meter -> asset) without duplicating those factories.
from tests.integration.phase1.conftest import (  # noqa: F401
    make_energy_asset,
    make_meter,
    make_site,
    make_user,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
MARKET_DATE = date(2026, 6, 2)
DELIVERY_START = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
DELIVERY_END = DELIVERY_START + timedelta(hours=1)


class StubMatchingEngine:
    """A deterministic price-time engine, sufficient to exercise the contract.

    Satisfies `MatchingEngine` structurally — no inheritance — which is the
    point: an implementation only has to match the shape.
    """

    def __init__(self, *, name: str = "stub", engine_version: str = "1.0.0") -> None:
        self._name = name
        self._version = engine_version
        self.calls: list[MatchingRequest] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def engine_version(self) -> str:
        return self._version

    def match(self, request: MatchingRequest) -> MatchingResult:
        self.calls.append(request)
        book = request.order_book
        remaining = {e.order_id: e.remaining_kwh for e in (*book.buys, *book.sells)}
        trades: list[ProposedTrade] = []

        # Price-time priority: best price first, then earliest arrival, then id.
        buys = sorted(
            book.buys,
            key=lambda e: (
                -(e.max_price_inr_per_kwh or Decimal("0")),
                e.created_at,
                str(e.order_id),
            ),
        )
        sells = sorted(
            book.sells,
            key=lambda e: (e.min_price_inr_per_kwh or Decimal("0"), e.created_at, str(e.order_id)),
        )

        for buy in buys:
            for sell in sells:
                if remaining[buy.order_id] <= Decimal("0"):
                    break
                if remaining[sell.order_id] <= Decimal("0"):
                    continue
                if not buy.overlaps(sell):
                    continue
                if not prices_cross(
                    buy_max_inr_per_kwh=buy.max_price_inr_per_kwh,
                    sell_min_inr_per_kwh=sell.min_price_inr_per_kwh,
                ):
                    continue

                quantity = min(remaining[buy.order_id], remaining[sell.order_id])
                assert buy.max_price_inr_per_kwh is not None
                assert sell.min_price_inr_per_kwh is not None
                trades.append(
                    ProposedTrade(
                        buy_order_id=buy.order_id,
                        sell_order_id=sell.order_id,
                        quantity_kwh=quantity,
                        clearing_price_inr_per_kwh=midpoint_clearing_price(
                            buy_max_inr_per_kwh=buy.max_price_inr_per_kwh,
                            sell_min_inr_per_kwh=sell.min_price_inr_per_kwh,
                        ),
                        delivery_start=max(buy.delivery_start, sell.delivery_start),
                        delivery_end=min(buy.delivery_end, sell.delivery_end),
                    )
                )
                remaining[buy.order_id] -= quantity
                remaining[sell.order_id] -= quantity

        return MatchingResult(
            engine=self._name,
            engine_version=self._version,
            trades=tuple(trades),
            unmatched_buy_order_ids=tuple(
                e.order_id for e in book.buys if remaining[e.order_id] > Decimal("0")
            ),
            unmatched_sell_order_ids=tuple(
                e.order_id for e in book.sells if remaining[e.order_id] > Decimal("0")
            ),
        )


class FailingMatchingEngine(StubMatchingEngine):
    """An engine that raises, to prove failures stay observable."""

    def match(self, request: MatchingRequest) -> MatchingResult:
        raise RuntimeError("optimiser did not converge")


class MisbehavingMatchingEngine(StubMatchingEngine):
    """An engine that satisfies the type but violates the contract."""

    def __init__(self, *, mode: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.mode = mode

    def match(self, request: MatchingRequest) -> MatchingResult:
        book = request.order_book
        buy = book.buys[0]
        sell = book.sells[0]
        common: dict[str, Any] = {
            "buy_order_id": buy.order_id,
            "sell_order_id": sell.order_id,
            "quantity_kwh": buy.remaining_kwh,
            "clearing_price_inr_per_kwh": Decimal("7"),
            "delivery_start": buy.delivery_start,
            "delivery_end": buy.delivery_end,
        }

        if self.mode == "over_fill":
            common["quantity_kwh"] = buy.remaining_kwh + Decimal("1000")
        elif self.mode == "unknown_order":
            common["buy_order_id"] = uuid.uuid4()
        elif self.mode == "wrong_side":
            common["buy_order_id"] = sell.order_id
            common["sell_order_id"] = sell.order_id
        elif self.mode == "zero_quantity":
            common["quantity_kwh"] = Decimal("0")
        elif self.mode == "negative_price":
            common["clearing_price_inr_per_kwh"] = Decimal("-1")
        elif self.mode == "empty_window":
            common["delivery_end"] = common["delivery_start"]

        return MatchingResult(
            engine=self._name,
            engine_version=self._version,
            trades=(ProposedTrade(**common),),
        )


# ---------------------------------------------------------------------------
# Registry fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_tradeable_user(
    db_session: Session,
    # These shadow the re-exports above, which is how pytest injects a fixture:
    # the parameter name *is* the lookup key, so it cannot be renamed.
    make_user: Callable[..., User],  # noqa: F811
    make_site: Callable[..., Site],  # noqa: F811
    make_meter: Callable[..., Meter],  # noqa: F811
    make_energy_asset: Callable[..., EnergyAsset],  # noqa: F811
) -> Callable[..., tuple[User, Site]]:
    """A user who passes the existing Phase 1 eligibility policy.

    Built by satisfying that policy's real inputs — DISCOM-verified utility
    account and meter, both consents, an active generation asset — rather than
    by bypassing it. Phase 4 must not create a second eligibility system.
    """

    def _make(*, role: UserRole = UserRole.PROSUMER) -> tuple[User, Site]:
        from app.db.models import VerificationRecord

        user = make_user(role=role, status=UserStatus.ACTIVE)
        site = make_site(owner_user_id=user.id)
        make_meter(site_id=site.id, verification_level=VerificationLevel.DISCOM_VERIFIED)
        asset = make_energy_asset(site_id=site.id, status=EnergyAssetStatus.ACTIVE)

        db_session.add(
            VerificationRecord(
                user_id=user.id,
                asset_id=asset.id,
                verification_type=VerificationType.UTILITY_ACCOUNT,
                source=VerificationSource.DISCOM,
                verification_level=VerificationLevel.DISCOM_VERIFIED,
                status=VerificationStatus.VERIFIED,
                verified_at=NOW,
            )
        )
        for scope in (ConsentScope.MARKET_PARTICIPATION, ConsentScope.METER_DATA):
            db_session.add(Consent(user_id=user.id, scope=scope))
        db_session.flush()
        return user, site

    return _make


@pytest.fixture
def order_defaults() -> dict[str, Any]:
    """Field values shared by the order-placing tests."""
    return {
        "side": OrderSide.BUY,
        "energy_kwh": Decimal("10.0"),
        "delivery_start": DELIVERY_START,
        "delivery_end": DELIVERY_END,
        "max_price_inr_per_kwh": Decimal("8.0"),
        "at": NOW,
    }
