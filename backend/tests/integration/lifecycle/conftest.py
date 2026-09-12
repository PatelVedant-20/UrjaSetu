"""One builder for the whole trade lifecycle.

Constructs the real entities each phase depends on — site and meter (Phase 1),
telemetry (Phase 2), a forecast run (Phase 3), a market session with a matched
trade (Phase 4), and the grid topology a validation needs (Phase 5) — so the
Phase 6-8 tests exercise the same objects the application does rather than
stand-ins.

Built directly rather than through each phase's service, so a failure in these
tests points at the phase under test instead of at the setup.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    EnergyAsset,
    ForecastPoint,
    ForecastRun,
    GridNode,
    MarketSession,
    Meter,
    Order,
    Site,
    TelemetryReading,
    Trade,
    User,
)
from app.domain.enums import (
    EnergyAssetStatus,
    EnergyAssetType,
    ForecastRunStatus,
    ForecastType,
    GridNodeType,
    MarketSessionStatus,
    MarketType,
    MeterType,
    OrderSide,
    TelemetryQualityStatus,
    TelemetrySource,
    UserRole,
    UserStatus,
)

# A delivery window in the past, so telemetry covering it is ordinary history
# rather than data from the future.
DELIVERY_START = datetime(2026, 6, 2, 6, 0, tzinfo=UTC)
DELIVERY_END = DELIVERY_START + timedelta(hours=1)
FEEDER = "FEEDER-E2E"

COMMITTED_KWH = Decimal("10.0000")
CLEARING_PRICE = Decimal("6.0000")
TRANSFORMER_RATING_KW = Decimal("250.0000")
LINE_RATING_KW = Decimal("60.0000")


@dataclass
class Lifecycle:
    """Everything one trade needs, already persisted."""

    buyer: User
    seller: User
    buyer_site: Site
    seller_site: Site
    seller_meter: Meter
    substation: GridNode
    transformer: GridNode
    buyer_node: GridNode
    seller_node: GridNode
    forecast_run: ForecastRun
    market_session: MarketSession
    buy_order: Order
    sell_order: Order
    trade: Trade


def _user(session: Session, label: str) -> User:
    user = User(
        display_name=f"{label} {uuid.uuid4().hex[:6]}",
        role=UserRole.PROSUMER,
        status=UserStatus.ACTIVE,
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.org",
    )
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def lifecycle(db_session: Session) -> Lifecycle:
    """A matched trade with every upstream artefact it references."""
    buyer = _user(db_session, "buyer")
    seller = _user(db_session, "seller")

    buyer_site = Site(owner_user_id=buyer.id, name="Buyer Site")
    seller_site = Site(owner_user_id=seller.id, name="Seller Site")
    db_session.add_all([buyer_site, seller_site])
    db_session.flush()

    # ---- Phase 5 topology: substation -> transformer -> two connection points
    substation = GridNode(
        external_ref=f"sub-{uuid.uuid4().hex[:8]}",
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11.0000"),
        feeder_id=FEEDER,
    )
    db_session.add(substation)
    db_session.flush()
    transformer = GridNode(
        external_ref=f"tx-{uuid.uuid4().hex[:8]}",
        node_type=GridNodeType.TRANSFORMER,
        nominal_voltage_kv=Decimal("0.4000"),
        parent_node_id=substation.id,
        feeder_id=FEEDER,
        rated_capacity_kw=TRANSFORMER_RATING_KW,
    )
    db_session.add(transformer)
    db_session.flush()
    buyer_node, seller_node = (
        GridNode(
            external_ref=f"cp-{uuid.uuid4().hex[:8]}",
            node_type=GridNodeType.CONNECTION_POINT,
            nominal_voltage_kv=Decimal("0.4000"),
            parent_node_id=transformer.id,
            feeder_id=FEEDER,
            rated_capacity_kw=LINE_RATING_KW,
        )
        for _ in range(2)
    )
    db_session.add_all([buyer_node, seller_node])
    db_session.flush()

    # ---- Phase 1 registry: a meter and an active PV asset for the seller
    seller_meter = Meter(
        site_id=seller_site.id,
        meter_type=MeterType.SMART_METER,
        external_meter_ref=f"m-{uuid.uuid4().hex[:8]}",
    )
    db_session.add(seller_meter)
    db_session.add(
        EnergyAsset(
            site_id=seller_site.id,
            asset_type=EnergyAssetType.PV,
            capacity_kw=Decimal("15.000"),
            status=EnergyAssetStatus.ACTIVE,
        )
    )
    db_session.flush()

    # ---- Phase 3: a completed forecast the sell order rests on
    forecast_run = ForecastRun(
        forecast_type=ForecastType.SOLAR,
        provider="baseline",
        model_version="1.0.0",
        horizon_start=DELIVERY_START,
        horizon_end=DELIVERY_END,
        status=ForecastRunStatus.COMPLETED,
    )
    db_session.add(forecast_run)
    db_session.flush()
    db_session.add(
        ForecastPoint(
            forecast_run_id=forecast_run.id,
            site_id=seller_site.id,
            interval_start=DELIVERY_START,
            interval_end=DELIVERY_END,
            predicted_kw=Decimal("10.0000"),
            predicted_kwh=Decimal("10.0000"),
            confidence=Decimal("0.9000"),
        )
    )

    # ---- Phase 4: an open session, two crossing orders and the matched trade
    market_session = MarketSession(
        market_date=date(2026, 6, 2),
        market_type=MarketType.DAY_AHEAD,
        status=MarketSessionStatus.OPEN,
    )
    db_session.add(market_session)
    db_session.flush()

    common = {
        "market_session_id": market_session.id,
        "delivery_start": DELIVERY_START,
        "delivery_end": DELIVERY_END,
        "energy_kwh": COMMITTED_KWH,
    }
    buy_order = Order(
        user_id=buyer.id,
        site_id=buyer_site.id,
        node_id=buyer_node.id,
        side=OrderSide.BUY,
        max_price_inr_per_kwh=Decimal("7.0000"),
        **common,
    )
    sell_order = Order(
        user_id=seller.id,
        site_id=seller_site.id,
        node_id=seller_node.id,
        side=OrderSide.SELL,
        min_price_inr_per_kwh=Decimal("5.0000"),
        forecast_basis_id=forecast_run.id,
        **common,
    )
    db_session.add_all([buy_order, sell_order])
    db_session.flush()

    trade = Trade(
        buy_order_id=buy_order.id,
        sell_order_id=sell_order.id,
        quantity_kwh=COMMITTED_KWH,
        clearing_price_inr_per_kwh=CLEARING_PRICE,
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        matching_engine="baseline",
        matching_engine_version="1.0.0",
    )
    db_session.add(trade)
    db_session.flush()

    return Lifecycle(
        buyer=buyer,
        seller=seller,
        buyer_site=buyer_site,
        seller_site=seller_site,
        seller_meter=seller_meter,
        substation=substation,
        transformer=transformer,
        buyer_node=buyer_node,
        seller_node=seller_node,
        forecast_run=forecast_run,
        market_session=market_session,
        buy_order=buy_order,
        sell_order=sell_order,
        trade=trade,
    )


@pytest.fixture
def deliver(db_session: Session, lifecycle: Lifecycle) -> Callable[[Decimal | None], None]:
    """Record what the seller's meter actually measured over the window.

    `None` writes a reading carrying no energy at all, which is how an
    unmeasured window differs from a measured zero.
    """

    def _deliver(energy_kwh: Decimal | None) -> None:
        db_session.add(
            TelemetryReading(
                meter_id=lifecycle.seller_meter.id,
                timestamp=DELIVERY_START,
                interval_start=DELIVERY_START,
                interval_end=DELIVERY_END,
                generation_kw=energy_kwh,
                energy_kwh=energy_kwh,
                quality_status=TelemetryQualityStatus.VALID,
                source=TelemetrySource.SIMULATOR,
            )
        )
        db_session.flush()

    return _deliver
