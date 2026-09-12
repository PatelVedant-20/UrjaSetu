"""Shared test fixtures for Phase-1 tests.

Provides a database session (PostgreSQL if running/reachable, or in-memory SQLite fallback
with StaticPool for local/isolated API contract tests) and a TestClient wired to the session.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Provide engine for Phase 1: PostgreSQL if reachable, SQLite fallback otherwise."""
    settings = get_settings()
    try:
        eng = build_engine(settings)
        with eng.connect() as connection:
            connection.execute(text("SELECT 1"))
        yield eng
        eng.dispose()
    except Exception:
        # Seamless in-memory fallback for local verification when Postgres is not running
        eng = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        yield eng
        eng.dispose()


@pytest.fixture(scope="session", autouse=True)
def init_phase1_tables(engine: Engine) -> None:
    """Ensure all declared tables (Phase 0 + Phase 1) exist in test database."""
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Transactional session rolled back after every test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def phase1_client(db_session: Session) -> Iterator[TestClient]:
    """TestClient wired to the transaction-isolated db_session."""
    app = create_app()

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
