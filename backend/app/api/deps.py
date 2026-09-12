"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
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
