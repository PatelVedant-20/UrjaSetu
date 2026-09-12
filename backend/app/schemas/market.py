"""API contracts for the Market resource group (docs/05_API_SPEC.md).

Transport-layer models only. These are not the domain contract: domain models
are in app.db.models.market and app.domain.interfaces.market.
Conversion between the two is explicit and one-directional.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    MarketSessionStatus,
    MarketType,
    OrderSide,
    OrderStatus,
    TradeStatus,
)


class MarketSessionCreate(BaseModel):
    """`POST /market/sessions` request body."""

    market_date: date
    market_type: MarketType = MarketType.DAY_AHEAD


class MarketSessionRead(BaseModel):
    """`POST /market/sessions`, `GET /market/sessions/{session_id}`, etc."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_date: date
    market_type: MarketType
    status: MarketSessionStatus
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    cleared_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OrderCreate(BaseModel):
    """`POST /orders` request body."""

    market_session_id: UUID
    user_id: UUID
    site_id: UUID
    node_id: UUID | None = None
    side: OrderSide
    energy_kwh: Decimal = Field(..., gt=0)
    min_price_inr_per_kwh: Decimal | None = Field(default=None, ge=0)
    max_price_inr_per_kwh: Decimal | None = Field(default=None, ge=0)
    delivery_start: datetime
    delivery_end: datetime
    forecast_basis_id: UUID | None = None
    reliability_score_snapshot: Decimal | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_order(self) -> OrderCreate:
        if self.delivery_end <= self.delivery_start:
            raise ValueError("delivery_end must be after delivery_start")
        if self.side is OrderSide.BUY and self.max_price_inr_per_kwh is None:
            raise ValueError("A buy order requires max_price_inr_per_kwh")
        if self.side is OrderSide.SELL and self.min_price_inr_per_kwh is None:
            raise ValueError("A sell order requires min_price_inr_per_kwh")
        return self


class OrderRead(BaseModel):
    """`POST /orders`, `GET /orders/{order_id}`, etc."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    market_session_id: UUID
    user_id: UUID
    site_id: UUID
    node_id: UUID | None = None
    side: OrderSide
    energy_kwh: Decimal
    matched_kwh: Decimal = Decimal("0")
    min_price_inr_per_kwh: Decimal | None = None
    max_price_inr_per_kwh: Decimal | None = None
    delivery_start: datetime
    delivery_end: datetime
    forecast_basis_id: UUID | None = None
    reliability_score_snapshot: Decimal | None = None
    status: OrderStatus
    created_at: datetime
    updated_at: datetime


class OrderBookEntryRead(BaseModel):
    """Entry in an order book."""

    model_config = ConfigDict(from_attributes=True)

    order_id: UUID
    side: OrderSide
    user_id: UUID
    site_id: UUID
    node_id: UUID | None = None
    remaining_kwh: Decimal
    delivery_start: datetime
    delivery_end: datetime
    created_at: datetime
    max_price_inr_per_kwh: Decimal | None = None
    min_price_inr_per_kwh: Decimal | None = None
    reliability_score_snapshot: Decimal | None = None


class OrderBookRead(BaseModel):
    """`GET /market/order-book` response."""

    model_config = ConfigDict(from_attributes=True)

    market_session_id: UUID
    market_date: date
    market_type: MarketType
    total_demand_kwh: Decimal
    total_supply_kwh: Decimal
    buys: list[OrderBookEntryRead] = Field(default_factory=list)
    sells: list[OrderBookEntryRead] = Field(default_factory=list)


class TradeRead(BaseModel):
    """`GET /trades/{trade_id}`, `POST /market/sessions/{session_id}/clear` item."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    buy_order_id: UUID
    sell_order_id: UUID
    quantity_kwh: Decimal
    clearing_price_inr_per_kwh: Decimal
    delivery_start: datetime
    delivery_end: datetime
    grid_validation_id: UUID | None = None
    status: TradeStatus
    committed_at: datetime | None = None
    matching_engine: str | None = None
    matching_engine_version: str | None = None
    created_at: datetime
    updated_at: datetime
