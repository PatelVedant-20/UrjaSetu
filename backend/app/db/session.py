"""SQLAlchemy engine and session management.

The only module that creates database connections. Routers never talk to the
database directly (docs/09_PHASE_0_SETUP.md Step 6); they depend on
`app.api.deps.get_db`, which is built on the session factory here.

Phase 0 uses the synchronous psycopg 3 driver. FastAPI runs sync dependencies
in a threadpool, so this is correct and materially simpler than async plumbing
we have no measured need for yet (docs/00_PROJECT_BIBLE.md: minimal complexity).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import DatabaseUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def build_engine(settings: Settings) -> Engine:
    """Create a configured engine. Used by the app and by Alembic alike."""
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        # Recycles connections that a restarted PostgreSQL has silently dropped,
        # which is the common failure after `docker compose restart db`.
        pool_pre_ping=settings.db_pool_pre_ping,
        echo=settings.db_echo,
        future=True,
    )


def get_engine() -> Engine:
    """Process-wide engine, created on first use.

    Lazy so that importing this module — which tests and tooling do freely —
    never opens a connection or requires PostgreSQL to be running.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = build_engine(settings)
        logger.info("Database engine created for %s", settings.safe_database_url())
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for non-request code (scripts, startup tasks).

    Commits on success, rolls back on any exception.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection() -> float:
    """Execute `SELECT 1` and return the round-trip time in milliseconds.

    This is a real query, not a socket check: it proves the credentials, the
    database name and the driver all work, which is what
    `GET /health/ready` needs to assert.

    Raises `DatabaseUnavailableError` — with the driver message and any
    connection string kept out of the client-facing payload.
    """
    started = time.perf_counter()
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Database connectivity check failed: %s", exc.__class__.__name__)
        raise DatabaseUnavailableError(details={"reason": exc.__class__.__name__}) from exc
    return round((time.perf_counter() - started) * 1000, 2)


def dispose_engine() -> None:
    """Close all pooled connections. Called on application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        logger.info("Database engine disposed")
    _engine = None
    _session_factory = None
