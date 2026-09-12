"""API metadata endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AppSettings
from app.schemas.common import MetaResponse

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse, summary="API version and enabled integrations")
def meta(settings: AppSettings) -> MetaResponse:
    """Describe this build to clients.

    `enabled_integrations` is empty in Phase 0 and grows as adapters land, so a
    client can discover which capabilities a deployment actually has instead of
    assuming them.
    """
    return MetaResponse(
        app=settings.app_name,
        version=settings.app_version,
        api_version="v1",
        environment=settings.app_env,
        market_mode=settings.market_mode,
        enabled_integrations=settings.enabled_integrations,
    )
