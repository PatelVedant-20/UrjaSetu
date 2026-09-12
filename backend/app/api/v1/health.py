"""Health and readiness endpoints.

Mounted at the application root (not under `/api/v1`) per docs/05_API_SPEC.md,
because orchestrators probe these independently of API versioning.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AppSettings
from app.core.errors import DatabaseUnavailableError
from app.db.session import check_database_connection
from app.schemas.common import (
    DependencyStatus,
    ErrorResponse,
    HealthResponse,
    ReadinessResponse,
)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Process health")
def health(settings: AppSettings) -> HealthResponse:
    """Liveness only.

    Deliberately performs no I/O: a database outage must not make the process
    look dead and get restarted in a loop. Readiness is what reports
    dependencies.
    """
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness — dependencies required by this deployment mode",
    responses={503: {"model": ErrorResponse, "description": "A dependency is unavailable"}},
)
def readiness() -> ReadinessResponse:
    """Verify every dependency the current deployment mode needs.

    In Phase 0 that is PostgreSQL alone, checked with a real `SELECT 1` rather
    than a socket probe.
    """
    try:
        latency_ms = check_database_connection()
    except DatabaseUnavailableError as exc:
        # Re-raised with the dependency report attached; the registered handler
        # renders it as the standard error envelope with a 503.
        raise DatabaseUnavailableError(
            details={
                "dependencies": [
                    DependencyStatus(
                        name="postgresql",
                        status="error",
                        detail=exc.details.get("reason", "connection failed"),
                    ).model_dump()
                ]
            }
        ) from exc

    return ReadinessResponse(
        status="ready",
        dependencies=[DependencyStatus(name="postgresql", status="ok", latency_ms=latency_ms)],
    )
