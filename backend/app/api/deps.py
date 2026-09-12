"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError
from app.db.models.identity import User
from app.db.session import get_session_factory


def get_db() -> Iterator[Session]:
    """Request-scoped database session.

    The session is closed when the request ends. Commits are the caller's
    responsibility so that a service can own its own transaction boundary
    (docs/04_DATA_MODEL.md, "Transaction Boundaries").
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_user(
    session: DbSession,
    x_user_id: Annotated[UUID | None, Header(alias="X-User-Id")] = None,
) -> User:
    """Resolve caller identity from the canonical X-User-Id header."""
    if x_user_id is None:
        raise UnauthorizedError(
            "Authentication required. Please supply a valid X-User-Id header.",
            details={"header": "X-User-Id"},
        )
    user = session.get(User, x_user_id)
    if user is None:
        raise UnauthorizedError(
            "Authenticated user not found.",
            details={"user_id": str(x_user_id)},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
