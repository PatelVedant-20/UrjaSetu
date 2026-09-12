"""Dynamic pricing orchestration.

    trade -> PricingRequest -> PricingEngine -> PricingResult -> price_components

Owns the transaction boundary for a pricing calculation and the assembly of
everything a price depends on. It contains **no formula**: it gathers the
inputs from their canonical owners, calls `engine.quote(...)`, checks the
result at the boundary and records it.

What it gathers, and from where:

* the **base price** from the Phase 4 trade (`clearing_price_inr_per_kwh`) —
  never recomputed here;
* the **grid state** from the Phase 5 validation run — status, metrics and the
  violations the trade caused;
* the **forecast confidence** from the Phase 3 run the *sell* order was placed
  against, because the seller is the party promising delivery;
* whether the trade is **local and renewable**, from the Phase 1 twin and asset
  registry.

It never approves, commits or modifies a trade, and it never overrules grid
validation. Phase 6 produces a price and a recommendation; acting on either
belongs to the phases that own trade state and settlement.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models.market import Order, Trade
from app.db.models.pricing import PriceComponents
from app.domain.enums import (
    EnergyAssetStatus,
    EnergyAssetType,
    GridValidationStatus,
    RealtimeEventType,
)
from app.domain.interfaces.grid import GridMetrics, GridViolation
from app.domain.interfaces.pricing import PricingEngine, PricingRequest, PricingResult
from app.domain.interfaces.realtime import RealtimeEvent, scalar
from app.domain.policies.dynamic_pricing import DEFAULT_ENGINE
from app.repositories import (
    EnergyAssetRepository,
    ForecastPointRepository,
    GridNodeRepository,
    GridValidationRunRepository,
    TradeRepository,
)
from app.repositories.pricing import PriceComponentsRepository
from app.services import audit_service
from app.services.realtime_service import publish as notify

ZERO = Decimal("0")


class PricingEngineError(UnprocessableError):
    """A pricing engine failed, or returned a result the contract does not allow."""

    code = "PRICING_ENGINE_FAILED"


# ---------------------------------------------------------------------------
# Quoting
# ---------------------------------------------------------------------------


def quote(request: PricingRequest, *, engine: PricingEngine = DEFAULT_ENGINE) -> PricingResult:
    """Price an explicit scenario.

    Takes no session: a quote is a pure calculation over values the caller has
    already assembled. This is what `POST /pricing/quote` is for — an
    explainable price *before* a trade exists, which is therefore not stored.
    """
    try:
        result = engine.quote(request)
    except Exception as exc:
        raise PricingEngineError(
            f"Pricing engine {engine.name!r} failed to produce a price.",
            details={"engine": engine.name, "reason": exc.__class__.__name__},
        ) from exc

    _validate_result(result, engine)
    return result


def quote_trade(
    session: Session, trade_id: UUID, *, engine: PricingEngine = DEFAULT_ENGINE
) -> PricingResult:
    """Price an existing trade without storing anything."""
    trade = _get_trade(session, trade_id)
    return quote(build_request(session, trade), engine=engine)


def price_trade(
    session: Session,
    trade_id: UUID,
    *,
    engine: PricingEngine = DEFAULT_ENGINE,
    at: datetime | None = None,
) -> PriceComponents:
    """Price a trade and record the breakdown. One transaction.

    The trade itself is left untouched: `trades.clearing_price_inr_per_kwh`
    remains the Phase 4 market clearing price, and the effective price lives in
    the breakdown. Overwriting the clearing price would destroy the baseline
    the components are explained against.
    """
    trade = _get_trade(session, trade_id)
    result = quote(build_request(session, trade), engine=engine)

    # Stamped from the application clock rather than left to the column's
    # `now()` default, which PostgreSQL evaluates once per *transaction*: two
    # breakdowns written in one transaction would share a timestamp, and
    # "the latest breakdown" — the price settlement pays against — would be
    # whichever row the database happened to return first.
    row = PriceComponents(
        created_at=at or datetime.now(UTC),
        trade_id=trade.id,
        base_market_price=result.base_market_price,
        time_component=result.time_component,
        congestion_component=result.congestion_component,
        imbalance_component=result.imbalance_component,
        local_renewable_component=result.local_renewable_component,
        final_price=result.final_price,
        formula_version=result.formula_version,
    )
    PriceComponentsRepository(session).add(row)
    session.flush()
    audit_service.record(
        session,
        audit_service.price_calculated(
            trade_id=trade.id,
            price_components_id=row.id,
            base_market_price=row.base_market_price,
            time_component=row.time_component,
            congestion_component=row.congestion_component,
            imbalance_component=row.imbalance_component,
            local_renewable_component=row.local_renewable_component,
            final_price=row.final_price,
            formula_version=row.formula_version,
            occurred_at=row.created_at or datetime.now(UTC),
        ),
    )
    session.commit()
    session.refresh(row)

    notify(
        RealtimeEvent(
            event_type=RealtimeEventType.MARKET_PRICE_CHANGED,
            entity_type="price_components",
            entity_id=row.id,
            trade_id=row.trade_id,
            payload={
                "base_market_price": scalar(row.base_market_price),
                "final_price": scalar(row.final_price),
                "formula_version": scalar(row.formula_version),
            },
        )
    )
    return row


def get_breakdown(session: Session, trade_id: UUID) -> PriceComponents:
    """The breakdown that currently applies to a trade.

    Backs `GET /trades/{trade_id}/price-breakdown`.
    """
    row = PriceComponentsRepository(session).latest_for_trade(trade_id)
    if row is None:
        raise NotFoundError(
            "No price breakdown has been calculated for this trade.",
            code="PRICE_BREAKDOWN_NOT_FOUND",
            details={"trade_id": str(trade_id)},
        )
    return row


# ---------------------------------------------------------------------------
# Assembling the inputs
# ---------------------------------------------------------------------------


def build_request(session: Session, trade: Trade) -> PricingRequest:
    """Collect everything the price depends on, from its canonical owner.

    Each input has exactly one source. Nothing is inferred from market volume
    or order counts: a busy market is not a constrained feeder, and pricing
    congestion from anything but the grid result would make the two
    indistinguishable.
    """
    status, metrics, caused, validation_id = _grid_state(session, trade)
    sell_order = session.get(Order, trade.sell_order_id)
    buy_order = session.get(Order, trade.buy_order_id)

    return PricingRequest(
        base_price_inr_per_kwh=trade.clearing_price_inr_per_kwh,
        quantity_kwh=trade.quantity_kwh,
        delivery_start=trade.delivery_start,
        delivery_end=trade.delivery_end,
        grid_status=status,
        grid_metrics=metrics,
        caused_violations=caused,
        forecast_confidence=_forecast_confidence(session, sell_order, trade),
        local_renewable=_is_local_renewable(session, buy_order, sell_order),
        trade_id=trade.id,
        grid_validation_id=validation_id,
        forecast_basis_id=sell_order.forecast_basis_id if sell_order else None,
    )


def _grid_state(
    session: Session, trade: Trade
) -> tuple[GridValidationStatus, GridMetrics | None, tuple[GridViolation, ...], UUID | None]:
    """The Phase 5 verdict for this trade.

    Prefers the run the trade itself cites, and falls back to the most recent
    run recorded against it. A trade with neither has never been validated,
    which is `UNKNOWN` — the same state as a validation that failed, because
    in both cases nobody has established that this trade is safe.

    `caused_violations` is empty on this path: `grid_validation_runs` stores
    the aggregate metrics and the verdict, not the individual violation
    objects, and reconstructing them from aggregates would invent detail the
    row does not hold. A caller that has just run a validation and still holds
    the live `GridValidationResult` can pass its violations straight into a
    `PricingRequest` instead.
    """
    runs = GridValidationRunRepository(session)
    run = None
    if trade.grid_validation_id is not None:
        run = runs.get(trade.grid_validation_id)
    if run is None:
        run = runs.latest_for_trade(trade.id)
    if run is None:
        return GridValidationStatus.UNKNOWN, None, (), None

    metrics = GridMetrics(
        min_voltage_pu=run.min_voltage_pu,
        max_voltage_pu=run.max_voltage_pu,
        max_line_loading_pct=run.max_line_loading_pct,
        max_transformer_loading_pct=run.max_transformer_loading_pct,
    )
    return run.status, metrics, (), run.id


def _forecast_confidence(
    session: Session, sell_order: Order | None, trade: Trade
) -> Decimal | None:
    """How confident the seller's forecast was over the delivery window.

    The **lowest** confidence of any forecast point covering the window, not
    the average: a trade is only as deliverable as its weakest interval, and
    averaging would let one confident hour conceal an uncertain one.

    `None` when the sell order cites no forecast, or when the provider reported
    no confidence — which the formula treats as an unknown, never as certainty.
    """
    if sell_order is None or sell_order.forecast_basis_id is None:
        return None

    points = ForecastPointRepository(session).list_for_run(sell_order.forecast_basis_id)
    covering = [
        point.confidence
        for point in points
        if point.confidence is not None
        and point.interval_start < trade.delivery_end
        and point.interval_end > trade.delivery_start
    ]
    return min(covering) if covering else None


def _is_local_renewable(
    session: Session, buy_order: Order | None, sell_order: Order | None
) -> bool:
    """Whether the trade earns the local-renewable incentive.

    Both halves must hold, and both are facts in the registry rather than
    judgements:

    * **local** — buyer and seller sit on the same feeder, so the energy does
      not traverse the upstream network. Read from `grid_nodes.feeder_id`;
      an order with no node, or a node with no feeder, cannot be shown to be
      local and therefore is not.
    * **renewable** — the seller's site has at least one active PV asset.
      `EnergyAssetType.PV` is the only renewable generation type the registry
      currently holds; batteries and EVs store energy rather than generate it.

    Neither half is assumed. A trade that cannot be shown to qualify does not,
    which keeps the incentive from becoming a blanket discount.
    """
    if buy_order is None or sell_order is None:
        return False
    if not _same_feeder(session, buy_order.node_id, sell_order.node_id):
        return False

    assets = EnergyAssetRepository(session).list_for_site(sell_order.site_id)
    return any(
        asset.asset_type is EnergyAssetType.PV and asset.status is EnergyAssetStatus.ACTIVE
        for asset in assets
    )


def _same_feeder(session: Session, buy_node_id: UUID | None, sell_node_id: UUID | None) -> bool:
    if buy_node_id is None or sell_node_id is None:
        return False

    nodes = GridNodeRepository(session)
    buy_node = nodes.get(buy_node_id)
    sell_node = nodes.get(sell_node_id)
    if buy_node is None or sell_node is None:
        return False
    if buy_node.feeder_id is None or sell_node.feeder_id is None:
        return False
    return buy_node.feeder_id == sell_node.feeder_id


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _get_trade(session: Session, trade_id: UUID) -> Trade:
    trade = TradeRepository(session).get(trade_id)
    if trade is None:
        raise NotFoundError(
            "Trade not found.", code="TRADE_NOT_FOUND", details={"trade_id": str(trade_id)}
        )
    return trade


def _validate_result(result: PricingResult, engine: PricingEngine) -> None:
    """Check an engine's output before trusting it.

    The important case is the first: a breakdown whose parts do not add up to
    its total does not explain the price it reports, and the database would
    reject it anyway. Failing here names the engine instead of surfacing a
    constraint violation from three layers down.
    """
    if result.components_sum != result.final_price:
        raise PricingEngineError(
            "Engine returned components that do not sum to the final price.",
            details={
                "engine": engine.name,
                "components_sum": str(result.components_sum),
                "final_price": str(result.final_price),
            },
        )
    if result.final_price < ZERO:
        raise PricingEngineError(
            "Engine returned a negative price.",
            details={"engine": engine.name, "final_price": str(result.final_price)},
        )
    if result.congestion_component < ZERO or result.imbalance_component < ZERO:
        raise PricingEngineError(
            "Congestion and imbalance are charges and must never pay the buyer.",
            details={"engine": engine.name},
        )
    if result.local_renewable_component > ZERO:
        raise PricingEngineError(
            "The local-renewable term is an incentive and must never be a charge.",
            details={"engine": engine.name},
        )
    if not result.formula_version:
        raise PricingEngineError(
            "Engine returned a result with no formula version.",
            details={"engine": engine.name},
        )
