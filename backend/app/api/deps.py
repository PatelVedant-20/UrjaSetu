"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
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
    request: Request,
    x_user_id: Annotated[UUID | None, Header(alias="X-User-Id")] = None,
) -> User:
    """Resolve caller identity from the canonical X-User-Id header."""
    from app.services.auth_service import COOKIE, resolve

    user = resolve(session, request.cookies.get(COOKIE))
    if user:
        return user
    settings = get_settings()
    if not (settings.app_env == "test" and settings.allow_legacy_test_api):
        raise UnauthorizedError("Please sign in.")
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
