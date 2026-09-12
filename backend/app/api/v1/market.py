"""Market API endpoints (docs/05_API_SPEC.md).

Transport only: parse, validate request shapes, delegate to
`app.services.market_service`, serialise responses.
No SQL, no business logic, no duplicate matching engines.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.domain.policies.market_matching import BaselineMatchingEngine
from app.schemas.common import ErrorResponse
from app.schemas.market import (
    MarketSessionCreate,
    MarketSessionRead,
    OrderBookRead,
    OrderCreate,
    OrderRead,
    TradeRead,
)
from app.services import market_service

router = APIRouter(tags=["market"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"}
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "Operation invalid in current state"}
}
UNPROCESSABLE: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Order or matching validation failed"}
}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.post(
    "/market/sessions",
    response_model=MarketSessionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create and open a market session",
    responses={**CONFLICT, **UNPROCESSABLE},
)
def create_market_session(payload: MarketSessionCreate, session: DbSession) -> MarketSessionRead:
    market_session = market_service.open_session(
        session,
        market_date=payload.market_date,
        market_type=payload.market_type,
    )
    return MarketSessionRead.model_validate(market_session)


@router.get(
    "/market/sessions/{session_id}",
    response_model=MarketSessionRead,
    summary="Get market session state",
    responses=NOT_FOUND,
)
def get_market_session(session_id: UUID, session: DbSession) -> MarketSessionRead:
    return MarketSessionRead.model_validate(market_service.get_session(session, session_id))


@router.post(
    "/market/sessions/{session_id}/close",
    response_model=MarketSessionRead,
    summary="Close order intake for a market session",
    responses={**NOT_FOUND, **CONFLICT},
)
def close_market_session(session_id: UUID, session: DbSession) -> MarketSessionRead:
    return MarketSessionRead.model_validate(market_service.close_session(session, session_id))


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@router.post(
    "/orders",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create buy or sell order",
    responses={**NOT_FOUND, **CONFLICT, **UNPROCESSABLE},
)
def create_order(payload: OrderCreate, session: DbSession) -> OrderRead:
    order = market_service.place_order(
        session,
        market_session_id=payload.market_session_id,
        user_id=payload.user_id,
        site_id=payload.site_id,
        node_id=payload.node_id,
        side=payload.side,
        energy_kwh=payload.energy_kwh,
        delivery_start=payload.delivery_start,
        delivery_end=payload.delivery_end,
        max_price_inr_per_kwh=payload.max_price_inr_per_kwh,
        min_price_inr_per_kwh=payload.min_price_inr_per_kwh,
        forecast_basis_id=payload.forecast_basis_id,
        reliability_score_snapshot=payload.reliability_score_snapshot,
    )
    return OrderRead.model_validate(order)


@router.get(
    "/orders/{order_id}",
    response_model=OrderRead,
    summary="Get order state",
    responses=NOT_FOUND,
)
def get_order(order_id: UUID, session: DbSession) -> OrderRead:
    return OrderRead.model_validate(market_service.get_order(session, order_id))


@router.post(
    "/orders/{order_id}/cancel",
    response_model=OrderRead,
    summary="Cancel an active order",
    responses={**NOT_FOUND, **CONFLICT},
)
def cancel_order(order_id: UUID, session: DbSession) -> OrderRead:
    return OrderRead.model_validate(market_service.cancel_order(session, order_id))


# ---------------------------------------------------------------------------
# Order Book
# ---------------------------------------------------------------------------


@router.get(
    "/market/order-book",
    response_model=OrderBookRead,
    summary="Get order book for a market session",
    responses=NOT_FOUND,
)
def get_order_book(
    session_id: Annotated[UUID, Query(description="Market session ID")],
    session: DbSession = None,  # type: ignore[assignment]
) -> OrderBookRead:
    order_book = market_service.build_order_book(session, session_id)
    return OrderBookRead.model_validate(order_book)


# ---------------------------------------------------------------------------
# Clearing & Trades
# ---------------------------------------------------------------------------


@router.post(
    "/market/sessions/{session_id}/clear",
    response_model=list[TradeRead],
    summary="Run matching and clearing for a closed market session",
    responses={**NOT_FOUND, **CONFLICT, **UNPROCESSABLE},
)
def clear_market_session(session_id: UUID, session: DbSession) -> list[TradeRead]:
    engine = BaselineMatchingEngine()
    trades = market_service.clear_session(session, session_id, engine=engine)
    return [TradeRead.model_validate(t) for t in trades]


@router.get(
    "/trades/{trade_id}",
    response_model=TradeRead,
    summary="Get trade state",
    responses=NOT_FOUND,
)
def get_trade(trade_id: UUID, session: DbSession) -> TradeRead:
    return TradeRead.model_validate(market_service.get_trade(session, trade_id))
