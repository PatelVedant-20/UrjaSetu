"""Shared API contracts.

These are transport-layer models only — no persistence logic
(docs/03_REPOSITORY_STRUCTURE.md ownership rules).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Body of the locked error envelope (docs/05_API_SPEC.md)."""

    code: str = Field(..., examples=["ORDER_VALIDATION_FAILED"])
    message: str = Field(..., examples=["Sell quantity exceeds eligible available energy."])
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(..., examples=["6f1c2d5e-0b1a-4f3c-9d8e-5a4b3c2d1e0f"])


class ErrorResponse(BaseModel):
    """Every non-2xx response in UrjaSetu has this shape."""

    error: ErrorDetail


class HealthResponse(BaseModel):
    """`GET /health` — process liveness. Performs no I/O."""

    status: Literal["ok"]
    app: str
    version: str
    environment: str


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "error"]
    detail: str | None = None
    latency_ms: float | None = None


class ReadinessResponse(BaseModel):
    """`GET /health/ready` — dependencies required by the current deployment mode."""

    status: Literal["ready", "not_ready"]
    dependencies: list[DependencyStatus]


class MetaResponse(BaseModel):
    """`GET /api/v1/meta` — API version, enabled integrations and market mode."""

    app: str
    version: str
    api_version: str
    environment: str
    market_mode: str
    enabled_integrations: list[str]
