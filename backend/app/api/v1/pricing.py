"""Dynamic Pricing API endpoints (docs/05_API_SPEC.md).

Transport only: parse, validate request shapes, delegate to
`app.services.pricing_service`, serialise responses.
No SQL, no business logic, no pricing math or formula calculation in routers.
The pricing engine and policies remain the sole owners of pricing behavior.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.schemas.common import ErrorResponse
from app.schemas.pricing import (
    PriceBreakdownRead,
    PricingQuoteRequest,
    PricingResultRead,
)
from app.services import pricing_service

router = APIRouter(tags=["pricing"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"}
}
UNPROCESSABLE: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Pricing engine error or invalid business state"}
}


@router.post(
    "/pricing/quote",
    response_model=PricingResultRead,
    status_code=status.HTTP_200_OK,
    summary="Calculate an explainable price before trade commitment",
    responses=UNPROCESSABLE,
)
def quote_price(payload: PricingQuoteRequest) -> PricingResultRead:
    """Calculate an explainable price quote for a prospective trade scenario.

    Pure calculation: does not open a DB transaction, does not mutate state.
    Delegates to PricingService and the active PricingEngine.
    """
    domain_request = payload.to_domain()
    result = pricing_service.quote(domain_request)
    return PricingResultRead.model_validate(result)


@router.get(
    "/trades/{trade_id}/price-breakdown",
    response_model=PriceBreakdownRead,
    summary="Return components and formula version for a trade",
    responses=NOT_FOUND,
)
def get_trade_price_breakdown(
    trade_id: UUID,
    session: DbSession,
) -> PriceBreakdownRead:
    """Return the authoritative price breakdown that currently applies to a trade."""
    breakdown = pricing_service.get_breakdown(session, trade_id)
    return PriceBreakdownRead.model_validate(breakdown)
