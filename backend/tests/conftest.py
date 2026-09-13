"""Shared test fixtures for the UrjaSetu backend.

These fixtures are the stable surface other team members build on
(docs/07_CODING_PHASES.md, Phase 0: "after Yagnik exposes stable app/db
fixtures"). Tests run against a real PostgreSQL instance — never SQLite — so
what passes here reflects the production database engine.

No fixture edits the database by hand: `make up` plus `make migrate` is the
only setup required.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import build_engine
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Historical phase contracts exercise retired service routes in an explicitly
# isolated test environment. The new workflow fixture turns compatibility OFF
# and checks real session authorization, origins and ownership.
os.environ["APP_ENV"] = "test"
os.environ["ALLOW_LEGACY_TEST_API"] = "true"
os.environ["SIMULATION_WORKER_ENABLED"] = "false"
get_settings.cache_clear()

# `.env` discovery lives in app.core.config, which resolves it by absolute path,
# so the suite behaves identically under `make test`, an IDE runner and CI.


@pytest.fixture(scope="session")
def settings() -> Iterator[Settings]:
    """Run persistence tests in a migrated disposable DB, never the live demo.

    Transaction rollback alone cannot give audit-genesis tests an empty chain
    when the developer is simultaneously trading in the application.
    """
    from app.db.session import dispose_engine

    base = get_settings()
    name = f"urjasetu_suite_{uuid.uuid4().hex[:12]}"
    url = with_database(base.database_url, name)
    admin = create_engine(maintenance_url(base), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        run_alembic_ok("upgrade", "head", db_url=url)
        with pytest.MonkeyPatch.context() as environment:
            environment.setenv("DATABASE_URL", url)
            dispose_engine()
            get_settings.cache_clear()
            yield get_settings()
    finally:
        dispose_engine()
        get_settings.cache_clear()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


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


# ---------------------------------------------------------------------------
# Migration helpers
#
# Migrations are proven against a throwaway database created per test, never
# against the development database — running them where the schema already
# exists proves nothing (docs/10_TESTING_AND_INTEGRATION.md: "migration test
# from clean DB").
# ---------------------------------------------------------------------------


def with_database(url: str, database: str) -> str:
    """Rebuild `url` pointing at a different database, keeping the password.

    `str(URL)` renders the password as `***`, so a URL rebuilt that way cannot
    authenticate. `render_as_string(hide_password=False)` is required whenever
    the result will be connected with.
    """
    return make_url(url).set(database=database).render_as_string(hide_password=False)


def maintenance_url(settings: Settings) -> str:
    """Connection to a database we are not about to create or drop."""
    if settings.maintenance_database_url:
        return settings.maintenance_database_url
    return with_database(settings.database_url, "postgres")


def run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke the Alembic CLI exactly as a developer or CI would."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={db_url}", *args],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def run_alembic_ok(*args: str, db_url: str) -> None:
    """Run Alembic and fail with a readable message if it did not succeed."""
    result = run_alembic(*args, db_url=db_url)
    if result.returncode != 0:
        pytest.fail(
            f"`alembic {' '.join(args)}` exited {result.returncode}.\n"
            f"stdout:\n{result.stdout}\n"
            "stderr (last 20 lines):\n" + "\n".join(result.stderr.splitlines()[-20:]),
            pytrace=False,
        )


@pytest.fixture
def empty_database(settings: Settings) -> Iterator[str]:
    """Create an empty throwaway database; drop it afterwards."""
    name = f"urjasetu_migtest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(maintenance_url(settings), isolation_level="AUTOCOMMIT")

    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # pragma: no cover - environment problem, not a defect
        admin.dispose()
        safe = Settings(database_url=maintenance_url(settings)).safe_database_url()
        pytest.fail(
            "Could not create a throwaway database for the migration test.\n"
            f"Maintenance URL: {safe}\nError: {exc.__class__.__name__}: {exc}",
            pytrace=False,
        )

    try:
        yield with_database(settings.database_url, name)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
