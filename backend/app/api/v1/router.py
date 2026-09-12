"""API v1 composition root.

Phase 2+ resource routers (telemetry, forecasts, market, grid, settlement,
audit) are registered here as they are implemented. Keeping composition in one
file is what makes the surface area of a phase reviewable.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    assets,
    audit,
    forecasts,
    market,
    meta,
    pricing,
    settlement,
    telemetry,
    users,
)

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(users.router)
api_router.include_router(assets.router)
api_router.include_router(telemetry.router)
api_router.include_router(forecasts.router)
# Phase 4. The module has existed since the market API was written; it was
# never registered, so every documented market endpoint returned 404.
api_router.include_router(market.router)
api_router.include_router(pricing.router)
api_router.include_router(settlement.router)
api_router.include_router(audit.router)
