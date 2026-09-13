"""Transactional orchestration for the connected demonstration.

One PostgreSQL row lock serializes community mutations and reservations. The
existing forecasting, matching, grid and pricing engines remain authoritative.
The simulation is explicitly isolated to one fictional feeder and never claims
utility verification or real money movement.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.adapters.forecast.baseline import BaselineForecastProvider
from app.adapters.grid.power_grid_model_adapter import PowerGridModelAdapter
from app.db.models import (
    AuditEventRecord,
    Consent,
    EnergyAsset,
    ForecastPoint,
    ForecastRun,
    GridNode,
    GridValidationRun,
    HouseholdProfile,
    JournalEntry,
    LoginCredential,
    MarketplaceAction,
    MarketSession,
    Meter,
    MeterReconciliation,
    Order,
    PriceComponents,
    Receipt,
    Settlement,
    Simulation,
    Site,
    TelemetryReading,
    Trade,
    TradeAllocation,
    User,
)
from app.domain.enums import (
    AuditEntityType,
    AuditEventType,
    ConsentScope,
    EnergyAssetStatus,
    EnergyAssetType,
    ForecastRunStatus,
    ForecastType,
    GridNodeType,
    GridValidationDecision,
    GridValidationStatus,
    MarketSessionStatus,
    MarketType,
    MeterType,
    OrderSide,
    OrderStatus,
    ReconciliationStatus,
    SettlementStatus,
    TelemetryQualityStatus,
    TelemetrySource,
    TradeStatus,
    UserRole,
    UserStatus,
    VerificationLevel,
)
from app.domain.interfaces.audit import AuditEvent
from app.domain.interfaces.forecasting import ForecastRequest, HistoricalObservation
from app.domain.interfaces.grid import GridValidationRequest, NodeInjection
from app.domain.interfaces.market import MatchingRequest, OrderBook, OrderBookEntry
from app.domain.interfaces.pricing import PricingRequest
from app.domain.policies.community_energy import INTERVAL, IST, VERSION, profile
from app.domain.policies.dynamic_pricing import DEFAULT_ENGINE
from app.domain.policies.grid_limits import DEFAULT_LIMITS
from app.domain.policies.market_matching import BaselineMatchingEngine
from app.services import audit_service
from app.services.auth_service import hash_password
from app.services.grid_validation_service import build_network

FEEDER = "AHMEDABAD-SIMULATION"
D = Decimal


def rows[T](db: Session, cls: type[T], *where: ColumnElement[bool]) -> list[T]:
    return list(db.scalars(select(cls).where(*where)))


def serialize(row: Any) -> dict[str, Any]:
    return {col.key: getattr(row, col.key) for col in inspect(row).mapper.column_attrs}


def state(db: Session, lock: bool = False) -> Simulation:
    query = select(Simulation).where(Simulation.id == 1)
    result = db.scalar(query.with_for_update() if lock else query)
    if not result:
        raise HTTPException(503, "Run the demo bootstrap command first.")
    return result


def bump(sim: Simulation) -> None:
    sim.revision += 1


def add_audit(
    db: Session,
    sim: Simulation,
    kind: str,
    entity: str,
    entity_id: UUID,
    payload: dict[str, Any],
    actor: UUID | None = None,
) -> None:
    audit_service.record(
        db,
        AuditEvent(
            event_id=uuid4(),
            event_type=AuditEventType(kind),
            entity_type=AuditEntityType(entity),
            entity_id=entity_id,
            event_time=sim.clock,
            recorded_at=datetime.now(UTC),
            actor_user_id=actor,
            payload=payload,
        ),
    )


def capacity(db: Session, site: Site) -> Decimal:
    return sum((x.capacity_kw for x in rows(db, EnergyAsset, EnergyAsset.site_id == site.id)), D(0))


def sites(db: Session) -> list[Site]:
    return rows(
        db, Site, Site.grid_node_id.in_(select(GridNode.id).where(GridNode.feeder_id == FEEDER))
    )


def reading_profile(
    moment: datetime, cap: Decimal, household: HouseholdProfile | None, scenario: str
) -> dict[str, Decimal]:
    if household:
        from app.domain.policies.household_energy import interval

        return interval(moment, float(cap), household.settings, str(household.user_id), scenario)
    return profile(moment, cap, consumer=cap == 0, scenario=scenario)


def add_reading(
    db: Session, site: Site, moment: datetime, scenario: str = "normal"
) -> TelemetryReading | None:
    meter = db.scalar(select(Meter).where(Meter.site_id == site.id))
    if meter is None:
        raise HTTPException(409, "Site has no configured meter.")
    previous = db.scalar(
        select(TelemetryReading).where(
            TelemetryReading.meter_id == meter.id, TelemetryReading.interval_start == moment
        )
    )
    if previous:
        return previous
    if scenario == "missing":
        return None
    cap = capacity(db, site)
    household = db.get(HouseholdProfile, site.owner_user_id)
    data = reading_profile(moment, cap, household, scenario)
    reading = TelemetryReading(
        meter_id=meter.id,
        timestamp=moment + INTERVAL,
        interval_start=moment,
        interval_end=moment + INTERVAL,
        **data,
        energy_kwh=data["load_kwh"],
        source=TelemetrySource.SIMULATOR,
        quality_status=TelemetryQualityStatus.VALID,
    )
    db.add(reading)
    return reading


def add_readings(
    db: Session, site: Site, moments: list[datetime], scenario: str = "normal"
) -> None:
    """Batch a site's profile generation; one meter/capacity lookup per batch."""
    if not moments or scenario == "missing":
        return
    meter = db.scalar(select(Meter).where(Meter.site_id == site.id))
    if meter is None:
        raise HTTPException(409, "Site has no configured meter.")
    existing = set(
        db.scalars(
            select(TelemetryReading.interval_start).where(
                TelemetryReading.meter_id == meter.id, TelemetryReading.interval_start.in_(moments)
            )
        )
    )
    cap = capacity(db, site)
    household = db.get(HouseholdProfile, site.owner_user_id)
    for moment in moments:
        if moment in existing:
            continue
        data = reading_profile(moment, cap, household, scenario)
        db.add(
            TelemetryReading(
                meter_id=meter.id,
                timestamp=moment + INTERVAL,
                interval_start=moment,
                interval_end=moment + INTERVAL,
                **data,
                energy_kwh=data["load_kwh"],
                source=TelemetrySource.SIMULATOR,
                quality_status=TelemetryQualityStatus.VALID,
            )
        )


def forecast(db: Session, site: Site, sim: Simulation) -> None:
    tomorrow = (
        (sim.clock.astimezone(IST) + timedelta(days=1))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )
    existing = db.scalar(
        select(ForecastPoint)
        .join(ForecastRun)
        .where(ForecastPoint.site_id == site.id, ForecastRun.horizon_start == tomorrow)
    )
    if existing:
        return
    readings = rows(
        db,
        TelemetryReading,
        TelemetryReading.meter_id.in_(select(Meter.id).where(Meter.site_id == site.id)),
        TelemetryReading.interval_end <= sim.clock,
        TelemetryReading.interval_start >= sim.clock - timedelta(days=8),
    )
    history = [
        HistoricalObservation(r.interval_start, r.interval_end, r.generation_kw, r.load_kw)
        for r in readings
    ]
    for kind in (ForecastType.SOLAR, ForecastType.LOAD):
        result = BaselineForecastProvider().predict(
            ForecastRequest(
                site.id, kind, tomorrow, tomorrow + timedelta(days=1), INTERVAL, history
            )
        )
        run = ForecastRun(
            forecast_type=kind,
            provider=result.provider,
            model_version=result.model_version,
            horizon_start=tomorrow,
            horizon_end=tomorrow + timedelta(days=1),
            status=ForecastRunStatus.COMPLETED,
        )
        db.add(run)
        db.flush()
        for point in result.points:
            db.add(ForecastPoint(forecast_run_id=run.id, site_id=site.id, **asdict(point)))
    db.flush()


def register(
    db: Session,
    sim: Simulation,
    email: str,
    password: str,
    name: str,
    role: str,
    pv_kw: Decimal | int = 6,
    setup: dict[str, Any] | None = None,
) -> User:
    email = email.lower().strip()
    if db.scalar(select(LoginCredential).where(LoginCredential.email == email)):
        raise HTTPException(409, "This email already has an account.")
    user = User(email=email, display_name=name, role=UserRole(role), status=UserStatus.ACTIVE)
    db.add(user)
    db.flush()
    db.add(LoginCredential(user_id=user.id, email=email, password_hash=hash_password(password)))
    if setup is not None:
        db.add(
            HouseholdProfile(
                user_id=user.id,
                settings={k: v for k, v in setup.items() if k not in ("avatar", "photo")},
                avatar=setup.get("avatar"),
                photo=setup.get("photo"),
            )
        )
    if role not in ("operator", "admin"):
        transformer = db.scalar(
            select(GridNode).where(GridNode.external_ref == FEEDER + "-transformer")
        )
        if transformer is None:
            raise HTTPException(503, "Community transformer is not configured.")
        node = GridNode(
            external_ref="house-" + str(user.id),
            node_type=GridNodeType.CONNECTION_POINT,
            nominal_voltage_kv=D("0.4"),
            parent_node_id=transformer.id,
            feeder_id=FEEDER,
            rated_capacity_kw=D("20"),
        )
        db.add(node)
        db.flush()
        site = Site(
            owner_user_id=user.id,
            name=name + " home",
            grid_node_id=node.id,
            latitude=D("23.0225"),
            longitude=D("72.5714"),
            timezone="Asia/Kolkata",
        )
        db.add(site)
        db.flush()
        db.add(
            Meter(
                site_id=site.id,
                meter_type=MeterType.SMART_METER,
                vendor="UrjaSetu synthetic meter",
                verification_level=VerificationLevel.SELF_DECLARED,
            )
        )
        if role == "prosumer":
            db.add(
                EnergyAsset(
                    site_id=site.id,
                    asset_type=EnergyAssetType.PV,
                    capacity_kw=D(str(pv_kw)),
                    status=EnergyAssetStatus.ACTIVE,
                )
            )
        for scope in (ConsentScope.METER_DATA, ConsentScope.MARKET_PARTICIPATION):
            db.add(Consent(user_id=user.id, scope=scope))
        db.flush()
        add_readings(
            db,
            site,
            [sim.clock - INTERVAL * i for i in range((30 if setup is not None else 7) * 96, 0, -1)],
        )
        db.flush()
        forecast(db, site, sim)
    bump(sim)
    return user


def bootstrap(db: Session, password: str) -> bool:
    if db.get(Simulation, 1):
        return False
    clock = datetime.now(IST).replace(hour=11, minute=45, second=0, microsecond=0).astimezone(UTC)
    sim = Simulation(id=1, clock=clock, running=False, scenario="normal", revision=0, weather={})
    db.add(sim)
    root = GridNode(
        external_ref=FEEDER + "-source",
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=D(11),
        feeder_id=FEEDER,
    )
    db.add(root)
    db.flush()
    db.add(
        GridNode(
            external_ref=FEEDER + "-transformer",
            node_type=GridNodeType.TRANSFORMER,
            nominal_voltage_kv=D("0.4"),
            parent_node_id=root.id,
            feeder_id=FEEDER,
            rated_capacity_kw=D(100),
        )
    )
    db.flush()
    register(db, sim, "asha@urjasetu.demo", password, "Asha Patel", "prosumer")
    register(db, sim, "ravi@urjasetu.demo", password, "Ravi Shah", "consumer")
    register(db, sim, "operator@urjasetu.demo", password, "Community operator", "operator")
    db.commit()
    return True


def prediction(db: Session, site_id: UUID, start: datetime) -> dict[str, ForecastPoint]:
    points = db.execute(
        select(ForecastPoint, ForecastRun.forecast_type)
        .join(ForecastRun)
        .where(ForecastPoint.site_id == site_id, ForecastPoint.interval_start == start)
        .order_by(ForecastRun.created_at.desc())
    ).all()
    found: dict[str, ForecastPoint] = {}
    for point, kind in points:
        found.setdefault(kind.value, point)
    if "solar" not in found or "load" not in found:
        raise HTTPException(
            409, "No complete forecast for that interval. Choose an available slot."
        )
    return found


def place_order(
    db: Session,
    user: User,
    start: datetime,
    side: str,
    quantity: Decimal,
    price: Decimal,
    *,
    commit: bool = True,
) -> Order:
    sim = state(db, True)
    start = start.astimezone(UTC)
    if start.second or start.microsecond or start.minute % 15:
        raise HTTPException(422, "Choose a 15-minute delivery boundary.")
    if start.astimezone(IST).date() != (sim.clock.astimezone(IST) + timedelta(days=1)).date():
        raise HTTPException(422, "Select an available delivery slot for tomorrow (IST).")
    site = db.scalar(select(Site).where(Site.owner_user_id == user.id))
    if not site or (side == "sell" and user.role != UserRole.PROSUMER):
        raise HTTPException(403, "This account cannot place that order.")
    basis = prediction(db, site.id, start)
    solar_kwh, load_kwh = basis["solar"].predicted_kwh, basis["load"].predicted_kwh
    if solar_kwh is None or load_kwh is None:
        raise HTTPException(409, "The forecast is missing interval energy.")
    if side == "sell":
        available = max(D(0), solar_kwh - load_kwh)
        reserved = sum(
            (
                x.matched_kwh + (x.remaining_kwh if x.status.is_active else D(0))
                for x in rows(
                    db,
                    Order,
                    Order.site_id == site.id,
                    Order.delivery_start == start,
                    Order.side == OrderSide.SELL,
                )
            ),
            D(0),
        )
        if quantity > available - reserved:
            raise HTTPException(
                409,
                f"Only {max(D(0), available-reserved):.4f} kWh remains after reservations.",
            )
    day = start.astimezone(IST).date()
    market = db.scalar(select(MarketSession).where(MarketSession.market_date == day))
    if not market:
        market = MarketSession(
            market_date=day,
            market_type=MarketType.DAY_AHEAD,
            status=MarketSessionStatus.OPEN,
            opened_at=sim.clock,
        )
        db.add(market)
        db.flush()
    order = Order(
        market_session_id=market.id,
        user_id=user.id,
        site_id=site.id,
        node_id=site.grid_node_id,
        side=OrderSide(side),
        energy_kwh=quantity,
        min_price_inr_per_kwh=price if side == "sell" else None,
        max_price_inr_per_kwh=price if side == "buy" else None,
        delivery_start=start,
        delivery_end=start + INTERVAL,
        forecast_basis_id=basis["solar"].forecast_run_id if side == "sell" else None,
        status=OrderStatus.OPEN,
        matched_kwh=D(0),
    )
    db.add(order)
    db.flush()
    add_audit(
        db,
        sim,
        "order_placed",
        "order",
        order.id,
        {
            "side": side,
            "energy_kwh": str(quantity),
            "limit_price": str(price),
            "source": "simulation",
        },
        user.id,
    )
    bump(sim)
    if commit:
        db.commit()
    return order


def cancel_order(db: Session, user: User, order_id: UUID) -> None:
    sim = state(db, True)
    order = db.get(Order, order_id)
    if not order or order.user_id != user.id:
        raise HTTPException(404, "Order not found.")
    if order.status != OrderStatus.OPEN or order.matched_kwh:
        raise HTTPException(409, "Only an unfilled open order can be cancelled.")
    order.status = OrderStatus.CANCELLED
    add_audit(db, sim, "order_cancelled", "order", order.id, {}, user.id)
    bump(sim)
    db.commit()


def accept_offer(
    db: Session,
    user: User,
    offer_id: UUID,
    quantity: Decimal,
    price: Decimal,
    request_id: UUID,
    own_order_id: UUID | None = None,
) -> Trade:
    """Atomic direct match; retries return the same trade and cannot spend twice."""
    state(db, True)
    body_hash = hashlib.sha256(
        f"{offer_id}|{quantity.normalize()}|{price.normalize()}|{own_order_id}".encode()
    ).hexdigest()
    previous = db.get(MarketplaceAction, (user.id, request_id))
    if previous:
        if previous.body_hash != body_hash:
            raise HTTPException(409, "This request ID was already used for another trade.")
        trade = db.get(Trade, previous.trade_id)
        assert trade is not None
        return trade
    offer = db.get(Order, offer_id)
    if not offer or not offer.status.is_active or offer.delivery_start <= state(db).clock:
        raise HTTPException(409, "This offer is no longer available. Refresh the marketplace.")
    if offer.user_id == user.id:
        raise HTTPException(409, "Choose another household's offer.")
    if quantity > offer.remaining_kwh:
        raise HTTPException(409, f"Only {offer.remaining_kwh:.4f} kWh is still available.")
    side = "buy" if offer.side == OrderSide.SELL else "sell"
    if own_order_id:
        own = db.get(Order, own_order_id)
        if not own or own.user_id != user.id:
            raise HTTPException(404, "Your order was not found.")
        if (
            not own.status.is_active
            or own.side.value != side
            or own.delivery_start != offer.delivery_start
            or own.remaining_kwh < quantity
        ):
            raise HTTPException(
                409,
                (
                    "Your order must have enough energy in the same delivery slot and "
                    "opposite direction."
                ),
            )
    else:
        own = place_order(db, user, offer.delivery_start, side, quantity, price, commit=False)
    result = clear_market(db, order_ids={own.id, offer.id}, quantity_cap=quantity, commit=False)
    if not result or result[0].status != TradeStatus.COMMITTED:
        # Request session rolls back: a failed direct purchase must not reject
        # another household's public order or leave a new reservation behind.
        raise HTTPException(
            409,
            (
                "Unable to match within both price limits and grid capacity. Try a "
                "different limit or delivery slot."
            ),
        )
    trade = result[0]
    db.add(
        MarketplaceAction(
            user_id=user.id, request_id=request_id, body_hash=body_hash, trade_id=trade.id
        )
    )
    db.commit()
    return trade


def validate_grid(db: Session, sim: Simulation, start: datetime) -> GridValidationRun:
    injections = []
    for site in sites(db):
        values = prediction(db, site.id, start)
        solar, load = values["solar"].predicted_kw, values["load"].predicted_kw
        if solar is None or load is None or site.grid_node_id is None:
            raise HTTPException(409, "Grid forecast or connection point is incomplete.")
        net = solar - load
        if sim.scenario == "congestion":
            net -= 65
        injections.append(NodeInjection(site.grid_node_id, net))
    request = GridValidationRequest(
        network=build_network(db, feeder_id=FEEDER, version=VERSION),
        limits=DEFAULT_LIMITS,
        interval_start=start,
        interval_end=start + INTERVAL,
        baseline_injections=tuple(injections),
    )
    # Trades allocate the forecast schedule. Do not inject its energy a second time.
    try:
        result = PowerGridModelAdapter().validate(request)
        metrics = asdict(result.metrics)
        status = result.status
        reason = (
            "; ".join(v.detail or v.violation_type.value for v in result.violations)
            or "Forecast schedule is within the modelled feeder limits."
        )
    except Exception as exc:
        metrics, status, reason = (
            {},
            GridValidationStatus.UNKNOWN,
            f"Solver unavailable: {type(exc).__name__}",
        )
    metrics = {
        k: v
        for k, v in metrics.items()
        if k
        in (
            "min_voltage_pu",
            "max_voltage_pu",
            "max_line_loading_pct",
            "max_transformer_loading_pct",
        )
    }
    row = GridValidationRun(
        simulation_engine="power_grid_model",
        engine_version=PowerGridModelAdapter().engine_version,
        input_hash=hashlib.sha256(repr(request).encode()).hexdigest(),
        status=status,
        decision=GridValidationDecision.ACCEPT
        if status == GridValidationStatus.SAFE
        else GridValidationDecision.REJECT,
        reason=reason,
        **metrics,
    )
    db.add(row)
    db.flush()
    return row


def clear_market(
    db: Session,
    *,
    order_ids: set[UUID] | None = None,
    quantity_cap: Decimal | None = None,
    commit: bool = True,
) -> list[Trade]:
    sim = state(db, True)
    open_orders = rows(
        db,
        Order,
        Order.status.in_([OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]),
        Order.delivery_start > sim.clock,
    )
    if order_ids is not None:
        open_orders = [o for o in open_orders if o.id in order_ids]
    trades = []
    for start in sorted({o.delivery_start for o in open_orders}):
        group = [o for o in open_orders if o.delivery_start == start]
        entries = [
            OrderBookEntry(
                order_id=o.id,
                side=o.side,
                user_id=o.user_id,
                site_id=o.site_id,
                node_id=o.node_id,
                remaining_kwh=min(o.remaining_kwh, quantity_cap)
                if quantity_cap is not None
                else o.remaining_kwh,
                delivery_start=o.delivery_start,
                delivery_end=o.delivery_end,
                created_at=o.created_at,
                min_price_inr_per_kwh=o.min_price_inr_per_kwh,
                max_price_inr_per_kwh=o.max_price_inr_per_kwh,
            )
            for o in group
        ]
        book = OrderBook(
            group[0].market_session_id,
            start.date(),
            MarketType.DAY_AHEAD,
            buys=[o for o in entries if o.side == OrderSide.BUY],
            sells=[o for o in entries if o.side == OrderSide.SELL],
        )
        result = BaselineMatchingEngine().match(MatchingRequest(book, sim.clock))
        if not result.trades:
            continue
        grid = validate_grid(db, sim, start)
        order_map = {o.id: o for o in group}
        for proposal in result.trades:
            buy, sell = order_map[proposal.buy_order_id], order_map[proposal.sell_order_id]
            if any(o.status == OrderStatus.REJECTED for o in (buy, sell)):
                continue
            if buy.user_id == sell.user_id:
                continue
            from app.domain.interfaces.grid import GridMetrics

            quote = DEFAULT_ENGINE.quote(
                PricingRequest(
                    base_price_inr_per_kwh=proposal.clearing_price_inr_per_kwh,
                    quantity_kwh=proposal.quantity_kwh,
                    delivery_start=start,
                    delivery_end=start + INTERVAL,
                    grid_status=grid.status,
                    grid_metrics=GridMetrics(
                        min_voltage_pu=grid.min_voltage_pu,
                        max_voltage_pu=grid.max_voltage_pu,
                        max_line_loading_pct=grid.max_line_loading_pct,
                        max_transformer_loading_pct=grid.max_transformer_loading_pct,
                    ),
                    forecast_confidence=prediction(db, sell.site_id, start)["solar"].confidence,
                    local_renewable=True,
                )
            )
            accepted = (
                grid.status == GridValidationStatus.SAFE
                and sell.min_price_inr_per_kwh is not None
                and buy.max_price_inr_per_kwh is not None
                and sell.min_price_inr_per_kwh <= quote.final_price <= buy.max_price_inr_per_kwh
            )
            trade = Trade(
                fill_sequence=1
                + (
                    db.scalar(
                        select(func.max(Trade.fill_sequence)).where(
                            Trade.buy_order_id == buy.id,
                            Trade.sell_order_id == sell.id,
                            Trade.delivery_start == start,
                        )
                    )
                    or 0
                ),
                buy_order_id=buy.id,
                sell_order_id=sell.id,
                quantity_kwh=proposal.quantity_kwh,
                clearing_price_inr_per_kwh=proposal.clearing_price_inr_per_kwh,
                delivery_start=start,
                delivery_end=start + INTERVAL,
                grid_validation_id=grid.id,
                status=TradeStatus.COMMITTED if accepted else TradeStatus.REJECTED,
                committed_at=sim.clock if accepted else None,
                matching_engine=result.engine,
                matching_engine_version=result.engine_version,
            )
            db.add(trade)
            db.flush()
            db.add(
                PriceComponents(
                    trade_id=trade.id,
                    base_market_price=quote.base_market_price,
                    time_component=quote.time_component,
                    congestion_component=quote.congestion_component,
                    imbalance_component=quote.imbalance_component,
                    local_renewable_component=quote.local_renewable_component,
                    final_price=quote.final_price,
                    formula_version=quote.formula_version,
                )
            )
            add_audit(
                db,
                sim,
                "trade_proposed",
                "trade",
                trade.id,
                {
                    "outcome": trade.status.value,
                    "grid": grid.status.value,
                    "final_price": str(quote.final_price),
                    "reason": grid.reason
                    if grid.status != GridValidationStatus.SAFE
                    else "Final price checked against both order limits.",
                },
            )
            for order in (buy, sell):
                if accepted:
                    order.matched_kwh += proposal.quantity_kwh
                    order.status = (
                        OrderStatus.FILLED
                        if order.remaining_kwh == 0
                        else OrderStatus.PARTIALLY_FILLED
                    )
                else:
                    order.status = OrderStatus.REJECTED
            trades.append(trade)
    bump(sim)
    if commit:
        db.commit()
    return trades


def reconcile_due(db: Session, sim: Simulation) -> None:
    for trade in db.scalars(
        select(Trade)
        .where(Trade.status == TradeStatus.COMMITTED, Trade.delivery_end <= sim.clock)
        .order_by(Trade.delivery_start, Trade.created_at, Trade.id)
    ):
        buy, sell = db.get(Order, trade.buy_order_id), db.get(Order, trade.sell_order_id)
        if buy is None or sell is None:
            raise HTTPException(409, "Trade order evidence is missing.")
        measured = []
        for order, channel, fk in (
            (sell, "grid_export_kwh", TradeAllocation.seller_reading_id),
            (buy, "grid_import_kwh", TradeAllocation.buyer_reading_id),
        ):
            meter = db.scalar(select(Meter).where(Meter.site_id == order.site_id))
            if meter is None:
                break
            reading = db.scalar(
                select(TelemetryReading).where(
                    TelemetryReading.meter_id == meter.id,
                    TelemetryReading.interval_start == trade.delivery_start,
                    TelemetryReading.interval_end == trade.delivery_end,
                    TelemetryReading.quality_status == TelemetryQualityStatus.VALID,
                )
            )
            if not reading or getattr(reading, channel) is None:
                break
            used = sum((a.energy_kwh for a in rows(db, TradeAllocation, fk == reading.id)), D(0))
            measured.append((reading, max(D(0), getattr(reading, channel) - used)))
        if len(measured) != 2:
            continue
        delivered = min(trade.quantity_kwh, measured[0][1], measured[1][1]).quantize(
            D("0.0001"), rounding=ROUND_DOWN
        )
        db.add(
            TradeAllocation(
                trade_id=trade.id,
                seller_reading_id=measured[0][0].id,
                buyer_reading_id=measured[1][0].id,
                energy_kwh=delivered,
            )
        )
        deviation = delivered - trade.quantity_kwh
        db.add(
            MeterReconciliation(
                trade_id=trade.id,
                committed_kwh=trade.quantity_kwh,
                actual_kwh=delivered,
                deviation_kwh=deviation,
                within_tolerance=abs(deviation) <= trade.quantity_kwh * D("0.05"),
                balancing_kwh=-deviation,
                reconciliation_status=ReconciliationStatus.RECONCILED,
                reason=(
                    "Synthetic bidirectional readings; chronological allocation capped by "
                    "seller export and buyer import. Shortfall remains with utility; "
                    "no invented penalty."
                ),
            )
        )
        price = db.scalar(select(PriceComponents).where(PriceComponents.trade_id == trade.id))
        grid = db.get(GridValidationRun, trade.grid_validation_id)
        if price is None or grid is None:
            raise HTTPException(409, "Trade price or grid evidence is missing.")
        gross = (delivered * price.final_price).quantize(D("0.01"))
        settlement = Settlement(
            trade_id=trade.id,
            buyer_user_id=buy.user_id,
            seller_user_id=sell.user_id,
            settled_kwh=delivered,
            gross_amount_inr=gross,
            platform_fee_inr=D(0),
            balancing_charge_inr=D(0),
            seller_credit_inr=gross,
            buyer_debit_inr=gross,
            status=SettlementStatus.SETTLED,
            settled_at=sim.clock,
        )
        db.add(settlement)
        db.flush()
        for account, amount in ((str(buy.user_id), -gross), (str(sell.user_id), gross)):
            db.add(JournalEntry(settlement_id=settlement.id, account=account, amount_inr=amount))
        trade.status = TradeStatus.SETTLED
        payload = {
            "schema": "urjasetu-receipt-1",
            "trade_id": str(trade.id),
            "settlement_id": str(settlement.id),
            "agreed_kwh": str(trade.quantity_kwh),
            "delivered_kwh": str(delivered),
            "price_inr_per_kwh": str(price.final_price),
            "gross_inr": str(gross),
            "delivery_start": trade.delivery_start.isoformat(),
            "grid_input_hash": grid.input_hash,
            "source": "synthetic",
            "model_version": VERSION,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        db.add(Receipt(trade_id=trade.id, payload=payload, payload_hash=digest, status="pending"))
        add_audit(
            db,
            sim,
            "trade_settled",
            "trade",
            trade.id,
            {"delivered_kwh": str(delivered), "gross_inr": str(gross), "receipt_hash": digest},
        )
        db.flush()


def advance(db: Session, intervals: int = 1, deliver: bool = False) -> Simulation:
    sim = state(db, True)
    target = sim.clock + INTERVAL * intervals
    if deliver:
        due = rows(db, Trade, Trade.status == TradeStatus.COMMITTED)
        if not due:
            raise HTTPException(409, "No committed trades await delivery.")
        target = max(t.delivery_end for t in due)
    if target > sim.clock + timedelta(days=2):
        raise HTTPException(422, "Advance at most two simulation days at a time.")
    all_sites = sites(db)
    moments = []
    while sim.clock < target:
        moments.append(sim.clock)
        sim.clock += INTERVAL
    for site in all_sites:
        add_readings(db, site, moments, sim.scenario)
    db.flush()
    reconcile_due(db, sim)
    for site in all_sites:
        forecast(db, site, sim)
    bump(sim)
    db.commit()
    return sim


def recover_missing(db: Session) -> None:
    """Replay missing demo delivery intervals with the normal synthetic profile.

    This is explicit operator replay, never fabricated utility measurement.
    Existing readings are immutable; add_reading returns them unchanged.
    """
    sim = state(db, True)
    for trade in rows(
        db, Trade, Trade.status == TradeStatus.COMMITTED, Trade.delivery_end <= sim.clock
    ):
        for order_id in (trade.buy_order_id, trade.sell_order_id):
            order = db.get(Order, order_id)
            site = db.get(Site, order.site_id) if order else None
            if site:
                add_reading(db, site, trade.delivery_start)
    db.flush()
    reconcile_due(db, sim)
    bump(sim)
    db.commit()


def snapshot(db: Session, user: User) -> dict[str, Any]:
    sim = state(db)
    tomorrow = (
        (sim.clock.astimezone(IST) + timedelta(days=1))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )
    own_sites = [s for s in sites(db) if s.owner_user_id == user.id]
    operator = user.role in (UserRole.OPERATOR, UserRole.ADMIN)
    own_orders = rows(db, Order, Order.user_id == user.id)
    own_ids = {o.id for o in own_orders}
    all_trades = rows(db, Trade)
    my_trades = [
        t for t in all_trades if operator or t.buy_order_id in own_ids or t.sell_order_id in own_ids
    ]
    trade_ids = {t.id for t in my_trades}
    readings = []
    forecasts = []
    for site in own_sites:
        readings += rows(
            db,
            TelemetryReading,
            TelemetryReading.meter_id.in_(select(Meter.id).where(Meter.site_id == site.id)),
            TelemetryReading.interval_start >= sim.clock - timedelta(days=1),
            TelemetryReading.interval_end <= sim.clock,
        )
        for point, kind in db.execute(
            select(ForecastPoint, ForecastRun.forecast_type)
            .join(ForecastRun)
            .where(
                ForecastPoint.site_id == site.id,
                ForecastPoint.interval_start >= tomorrow,
                ForecastPoint.interval_start < tomorrow + timedelta(days=1),
            )
        ).all():
            forecasts.append({**serialize(point), "kind": kind.value})
    settlements = [s for s in rows(db, Settlement) if s.trade_id in trade_ids]
    book = rows(
        db,
        Order,
        Order.status.in_([OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]),
        Order.delivery_start > sim.clock,
    )
    members = list(
        db.scalars(select(User).join(LoginCredential).where(User.status == UserStatus.ACTIVE))
    )
    prices = [p for p in rows(db, PriceComponents) if p.trade_id in trade_ids]
    market_prices = [
        {
            "delivery_start": t.delivery_start,
            "price": t.clearing_price_inr_per_kwh,
            "quantity": t.quantity_kwh,
            "status": t.status.value,
        }
        for t in all_trades
        if t.status != TradeStatus.REJECTED
    ]
    # Shared aggregate only: other households' individual measurements stay private.
    grid_series = [
        {
            "interval_start": moment,
            "generation_kw": generation,
            "load_kw": load,
            "meter_count": count,
            "expected_meters": len(sites(db)),
        }
        for moment, generation, load, count in db.execute(
            select(
                TelemetryReading.interval_start,
                func.sum(TelemetryReading.generation_kw),
                func.sum(TelemetryReading.load_kw),
                func.count(TelemetryReading.id),
            )
            .join(Meter, TelemetryReading.meter_id == Meter.id)
            .where(
                Meter.site_id.in_([s.id for s in sites(db)]),
                TelemetryReading.interval_start >= sim.clock - timedelta(days=1),
                TelemetryReading.interval_end <= sim.clock,
                TelemetryReading.quality_status == TelemetryQualityStatus.VALID,
            )
            .group_by(TelemetryReading.interval_start)
            .order_by(TelemetryReading.interval_start)
        ).all()
    ]
    return {
        "user": {
            "id": user.id,
            "name": user.display_name,
            "email": user.email,
            "role": user.role.value,
        },
        "simulation": {
            **serialize(sim),
            "source": "Synthetic Gujarat household profiles",
            "model_version": VERSION,
        },
        "sites": [
            {
                **serialize(s),
                "capacity_kw": capacity(db, s),
                "verification": "Demo only · self-declared",
            }
            for s in own_sites
        ],
        "readings": [serialize(r) for r in sorted(readings, key=lambda r: r.interval_start)],
        "forecasts": sorted(forecasts, key=lambda p: str(p["interval_start"])),
        "orders": [serialize(o) for o in own_orders],
        "order_book": [
            {
                "id": o.id,
                "side": o.side.value,
                "energy_kwh": o.remaining_kwh,
                "price": o.min_price_inr_per_kwh
                if o.side == OrderSide.SELL
                else o.max_price_inr_per_kwh,
                "delivery_start": o.delivery_start,
                "mine": o.user_id == user.id,
            }
            for o in book
        ],
        "trades": [
            {**serialize(t), "side": "buy" if t.buy_order_id in own_ids else "sell"}
            for t in my_trades
        ],
        "prices": [serialize(p) for p in prices],
        "market_prices": market_prices,
        "grid_series": grid_series,
        "grid": [
            serialize(g)
            for g in db.scalars(
                select(GridValidationRun).order_by(GridValidationRun.created_at.desc())
            )
        ],
        "nodes": [serialize(n) for n in rows(db, GridNode, GridNode.feeder_id == FEEDER)],
        "settlements": [serialize(s) for s in settlements],
        "reconciliations": [
            serialize(r) for r in rows(db, MeterReconciliation) if r.trade_id in trade_ids
        ],
        "receipts": [serialize(r) for r in rows(db, Receipt) if r.trade_id in trade_ids],
        "journal": [
            serialize(j)
            for j in rows(db, JournalEntry)
            if j.settlement_id in {s.id for s in settlements}
        ],
        "audit": [
            serialize(a) for a in rows(db, AuditEventRecord) if a.entity_id in trade_ids | own_ids
        ],
        "community": [{"id": m.id, "name": m.display_name, "role": m.role.value} for m in members],
        "portfolio": {
            "earned_inr": sum(
                (s.seller_credit_inr for s in settlements if s.seller_user_id == user.id), D(0)
            ),
            "spent_inr": sum(
                (s.buyer_debit_inr for s in settlements if s.buyer_user_id == user.id), D(0)
            ),
            "traded_kwh": sum((s.settled_kwh for s in settlements), D(0)),
            "money_mode": "Simulated accounting",
        },
    }
