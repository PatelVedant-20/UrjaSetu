"""API contracts for Settlement and Reconciliation (docs/05_API_SPEC.md).

Transport-layer models only: parse, validate, serialize.
Routers and schemas contain no settlement arithmetic, deviation calculation,
tolerance logic, fee percentages, or ledger balancing. All business logic
is strictly owned by SettlementService and SettlementCalculator.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ReconciliationStatus, SettlementStatus


class MeterReconciliationRead(BaseModel):
    """`POST /trades/{trade_id}/reconcile` response body (Entity 19).

    Serializes stored MeterReconciliation record comparing committed vs actual energy.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trade_id: UUID
    committed_kwh: Decimal = Field(..., description="Agreed energy commitment in kWh")
    actual_kwh: Decimal | None = Field(
        default=None,
        description="Measured actual energy in kWh (NULL if unmeasured)",
    )
    deviation_kwh: Decimal | None = Field(
        default=None,
        description="Signed deviation in kWh (actual - committed)",
    )
    within_tolerance: bool = Field(
        ...,
        description="Whether deviation is within allowable tolerance band",
    )
    balancing_kwh: Decimal = Field(
        ...,
        description="Shortfall volume covered by the grid in kWh",
    )
    reconciliation_status: ReconciliationStatus = Field(
        ...,
        description="Reconciliation verdict status",
    )
    reason: str | None = Field(
        default=None,
        description="Explanatory prose produced by the reconciliation policy",
    )
    created_at: datetime
    updated_at: datetime


class SettlementRead(BaseModel):
    """`POST /trades/{trade_id}/settle`, `GET /settlements/{settlement_id}`,
    and `GET /users/{user_id}/settlements` response body (Entity 20).

    Serializes stored Settlement financial allocation record.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trade_id: UUID
    buyer_user_id: UUID
    seller_user_id: UUID
    settled_kwh: Decimal = Field(..., description="Final settled energy volume in kWh")
    gross_amount_inr: Decimal = Field(
        ...,
        description="Gross trade value in INR (settled_kwh * effective_price)",
    )
    platform_fee_inr: Decimal = Field(..., description="Platform fee retained in INR")
    balancing_charge_inr: Decimal = Field(
        ...,
        description="Balancing charge for grid-supplied shortfall in INR",
    )
    seller_credit_inr: Decimal = Field(
        ...,
        description="Net amount credited to seller in INR",
    )
    buyer_debit_inr: Decimal = Field(
        ...,
        description="Total amount debited from buyer in INR",
    )
    status: SettlementStatus = Field(..., description="Settlement state")
    settled_at: datetime = Field(..., description="Timestamp of settlement execution")
    created_at: datetime
    updated_at: datetime


class SettlementLineRead(BaseModel):
    """Itemized breakdown line for an auditable settlement."""

    model_config = ConfigDict(from_attributes=True)

    label: str
    quantity_kwh: Decimal | None = None
    price_inr_per_kwh: Decimal | None = None
    amount_inr: Decimal
    reason: str


class ReconciliationOutcomeRead(BaseModel):
    """Domain reconciliation outcome contract representation."""

    model_config = ConfigDict(from_attributes=True)

    committed_quantity_kwh: Decimal
    actual_quantity_kwh: Decimal | None = None
    deviation_kwh: Decimal | None = None
    deviation_pct: Decimal | None = None
    within_tolerance: bool
    balancing_kwh: Decimal
    settled_quantity_kwh: Decimal | None = None
    status: ReconciliationStatus
    reason: str
    policy_version: str


class SettlementResultRead(BaseModel):
    """Domain SettlementResult contract representation."""

    model_config = ConfigDict(from_attributes=True)

    trade_id: UUID
    buyer_user_id: UUID
    seller_user_id: UUID
    settled_quantity_kwh: Decimal
    effective_price_inr_per_kwh: Decimal
    gross_amount_inr: Decimal
    platform_fee_inr: Decimal
    balancing_charge_inr: Decimal
    buyer_debit_inr: Decimal
    seller_credit_inr: Decimal
    status: SettlementStatus
    policy_version: str
    reconciliation: ReconciliationOutcomeRead
    price_components_id: UUID | None = None
    forecast_basis_id: UUID | None = None
    grid_validation_id: UUID | None = None
    lines: list[SettlementLineRead] = Field(default_factory=list)
