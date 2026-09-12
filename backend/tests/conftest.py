"""Shared test fixtures for the UrjaSetu backend.

These fixtures are the stable surface other team members build on
(docs/07_CODING_PHASES.md, Phase 0: "after Yagnik exposes stable app/db
fixtures"). Tests run against a real PostgreSQL instance — never SQLite — so
what passes here reflects the production database engine.

No fixture edits the database by hand: `make up` plus `make migrate` is the
only setup required.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import build_engine
from app.main import create_app

# `.env` discovery lives in app.core.config, which resolves it by absolute path,
# so the suite behaves identically under `make test`, an IDE runner and CI.


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def engine(settings: Settings) -> Iterator[Engine]:
    """Session-wide engine, verified before any test runs.

    Fails with an actionable message rather than letting every downstream test
    fail with an opaque driver error.
    """
    eng = build_engine(settings)
    try:
        with eng.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        eng.dispose()
        pytest.fail(
            "Cannot reach PostgreSQL at "
            f"{settings.safe_database_url()}.\n"
            "Start it and apply migrations first:\n"
            "    make up && make migrate\n"
            f"Driver error: {exc.__class__.__name__}",
            pytrace=False,
        )
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Transactional session that is rolled back after every test.

    The test runs inside an outer transaction that is never committed, so tests
    never leave rows behind and cannot affect each other's state.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        # A failed flush (e.g. an IntegrityError assertion) already aborts and
        # deassociates this transaction, so rolling it back again warns.
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FastAPI test client with the application lifespan executed."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
