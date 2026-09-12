"""Services — coordinate repositories and own transaction boundaries.

A service knows nothing about HTTP: it takes plain values and domain types,
raises domain errors, and returns persistence or domain objects. Translating
those errors into status codes is the router's job, handled once by the
exception handlers in `app.core.errors`.

The two error classes below are shared by every service in this layer. They
subclass the existing `UrjaSetuError`, so they render through the locked error
envelope from docs/05_API_SPEC.md without needing a new handler.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import status

from app.core.errors import UrjaSetuError


class ResourceNotFoundError(UrjaSetuError):
    """A referenced entity does not exist."""

    http_status = status.HTTP_404_NOT_FOUND

    def __init__(self, resource: str, resource_id: UUID | str) -> None:
        super().__init__(
            f"{resource.replace('_', ' ').capitalize()} not found.",
            code=f"{resource.upper()}_NOT_FOUND",
            details={"id": str(resource_id)},
        )


class ResourceConflictError(UrjaSetuError):
    """A write would violate a uniqueness or integrity rule."""

    http_status = status.HTTP_409_CONFLICT

    def __init__(
        self,
        message: str,
        *,
        code: str = "RESOURCE_CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, details=details)


__all__ = ["ResourceConflictError", "ResourceNotFoundError"]
