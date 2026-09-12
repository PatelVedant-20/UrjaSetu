"""API contracts for Dynamic Pricing (docs/05_API_SPEC.md).

Transport-layer models only: parse, validate, serialize.
The router and schemas contain no pricing arithmetic, no formula logic,
and no thresholds. Business logic is owned by PricingService and PricingEngine.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    GridValidationDecision,
    GridValidationStatus,
    GridViolationType,
    PriceComponentKind,
)
from app.domain.interfaces.grid import GridMetrics, GridViolation
from app.domain.interfaces.pricing import PricingRequest


class PriceComponentRead(BaseModel):
    """One itemized adjustment term in an explainable price."""

    model_config = ConfigDict(from_attributes=True)

    kind: PriceComponentKind
    amount_inr_per_kwh: Decimal
    reason: str


class GridMetricsInput(BaseModel):
    """Normalized grid state metrics for price calculation."""

    min_voltage_pu: Decimal | None = Field(default=None, ge=0)
    max_voltage_pu: Decimal | None = Field(default=None, ge=0)
    max_line_loading_pct: Decimal | None = Field(default=None, ge=0)
    max_transformer_loading_pct: Decimal | None = Field(default=None, ge=0)


class GridViolationInput(BaseModel):
    """Breached grid constraint input for price calculation."""

    violation_type: GridViolationType
    element_id: UUID | None = None
    observed: Decimal
    limit: Decimal
    detail: str | None = None


class PricingQuoteRequest(BaseModel):
    """`POST /pricing/quote` request body.

    Used to obtain an explainable quote before trade commitment.
    """

    base_price_inr_per_kwh: Decimal = Field(..., ge=0, description="Base clearing price in INR/kWh")
    quantity_kwh: Decimal = Field(..., gt=0, description="Energy quantity in kWh")
    delivery_start: datetime = Field(..., description="Start of delivery window in ISO-8601 UTC")
    delivery_end: datetime = Field(..., description="End of delivery window in ISO-8601 UTC")

    grid_status: GridValidationStatus = Field(
        default=GridValidationStatus.UNKNOWN,
        description="Phase 5 grid validation verdict (defaults to UNKNOWN)",
    )
    grid_metrics: GridMetricsInput | None = Field(
        default=None,
        description="Measured grid metrics if validation was run",
    )
    caused_violations: list[GridViolationInput] = Field(
        default_factory=list,
        description="Violations attributed to this trade",
    )
    forecast_confidence: Decimal | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Seller forecast confidence in [0, 1]",
    )
    local_renewable: bool = Field(
        default=False,
        description="Whether trade qualifies for local renewable incentive",
    )

    trade_id: UUID | None = Field(default=None, description="Optional associated trade ID")
    grid_validation_id: UUID | None = Field(default=None, description="Optional grid validation run ID")
    forecast_basis_id: UUID | None = Field(default=None, description="Optional forecast run ID")

    @model_validator(mode="after")
    def _validate_window(self) -> PricingQuoteRequest:
        if self.delivery_end <= self.delivery_start:
            raise ValueError("delivery_end must be after delivery_start")
        return self

    def to_domain(self) -> PricingRequest:
        """Map validated request to pure canonical domain PricingRequest."""
        metrics = None
        if self.grid_metrics is not None:
            metrics = GridMetrics(
                min_voltage_pu=self.grid_metrics.min_voltage_pu,
                max_voltage_pu=self.grid_metrics.max_voltage_pu,
                max_line_loading_pct=self.grid_metrics.max_line_loading_pct,
                max_transformer_loading_pct=self.grid_metrics.max_transformer_loading_pct,
            )
        violations = tuple(
            GridViolation(
                violation_type=v.violation_type,
                element_id=v.element_id,
                observed=v.observed,
                limit=v.limit,
                detail=v.detail,
            )
            for v in self.caused_violations
        )
        return PricingRequest(
            base_price_inr_per_kwh=self.base_price_inr_per_kwh,
            quantity_kwh=self.quantity_kwh,
            delivery_start=self.delivery_start,
            delivery_end=self.delivery_end,
            grid_status=self.grid_status,
            grid_metrics=metrics,
            caused_violations=violations,
            forecast_confidence=self.forecast_confidence,
            local_renewable=self.local_renewable,
            trade_id=self.trade_id,
            grid_validation_id=self.grid_validation_id,
            forecast_basis_id=self.forecast_basis_id,
        )


class PricingResultRead(BaseModel):
    """`POST /pricing/quote` response body.

    Exposes the canonical pricing calculation and breakdown.
    All field names match the canonical domain PricingResult.
    """

    model_config = ConfigDict(from_attributes=True)

    formula_version: str
    engine: str
    base_market_price: Decimal
    time_component: Decimal
    congestion_component: Decimal
    imbalance_component: Decimal
    local_renewable_component: Decimal
    final_price: Decimal
    components: list[PriceComponentRead] = Field(default_factory=list)
    recommended_decision: GridValidationDecision
    grid_status: GridValidationStatus


class PriceBreakdownRead(BaseModel):
    """`GET /trades/{trade_id}/price-breakdown` response body.

    Serializes stored PriceComponents (Entity 18 of docs/04_DATA_MODEL.md).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trade_id: UUID
    base_market_price: Decimal
    time_component: Decimal
    congestion_component: Decimal
    imbalance_component: Decimal
    local_renewable_component: Decimal
    final_price: Decimal
    formula_version: str
    created_at: datetime
    updated_at: datetime
