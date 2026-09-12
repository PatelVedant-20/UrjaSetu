"""Phase 0 gate: `alembic upgrade head` works from a genuinely empty database.

Running migrations against the already-migrated development database would
prove nothing. These tests create a throwaway database, migrate it from
nothing, assert the resulting schema, roll it back and drop it — so the suite
needs no manual database preparation (docs/09_PHASE_0_SETUP.md Step 10) and
satisfies the rule in docs/10_TESTING_AND_INTEGRATION.md that every schema
change is proven from a clean database.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _with_database(url: str, database: str) -> str:
    """Rebuild `url` pointing at a different database, keeping the password.

    `str(URL)` renders the password as `***`, so a URL rebuilt that way cannot
    actually authenticate. `render_as_string(hide_password=False)` is required
    whenever the result is going to be connected with.
    """
    return make_url(url).set(database=database).render_as_string(hide_password=False)


def _maintenance_url(settings: Settings) -> str:
    """Connection to a database we are not about to create or drop."""
    if settings.maintenance_database_url:
        return settings.maintenance_database_url
    return _with_database(settings.database_url, "postgres")


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke the Alembic CLI exactly as a developer or CI would."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={db_url}", *args],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_alembic_ok(*args: str, db_url: str) -> None:
    """Run Alembic and fail with a readable message if it did not succeed."""
    result = _run_alembic(*args, db_url=db_url)
    if result.returncode != 0:
        pytest.fail(
            f"`alembic {' '.join(args)}` exited {result.returncode}.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr (last 20 lines):\n" + "\n".join(result.stderr.splitlines()[-20:]),
            pytrace=False,
        )


@pytest.fixture
def empty_database(settings: Settings) -> Iterator[str]:
    """Create an empty throwaway database; drop it afterwards."""
    name = f"urjasetu_migtest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(_maintenance_url(settings), isolation_level="AUTOCOMMIT")

    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # pragma: no cover - environment problem, not a code defect
        admin.dispose()
        safe_url = Settings(database_url=_maintenance_url(settings)).safe_database_url()
        pytest.fail(
            "Could not create a throwaway database for the migration smoke test.\n"
            f"Maintenance URL: {safe_url}\n"
            f"Error: {exc.__class__.__name__}: {exc}",
            pytrace=False,
        )

    target_url = _with_database(settings.database_url, name)
    try:
        yield target_url
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_upgrade_head_from_empty_database(empty_database: str) -> None:
    result = _run_alembic("upgrade", "head", db_url=empty_database)

    assert (
        result.returncode == 0
    ), f"alembic upgrade head failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    engine = create_engine(empty_database)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "system_metadata" in tables
        assert "alembic_version" in tables

        columns = {col["name"] for col in inspector.get_columns("system_metadata")}
        assert columns == {"id", "key", "value", "created_at", "updated_at"}

        # The naming convention from app/db/base.py must survive into the
        # real schema, or later migrations cannot reference constraints by name.
        index_names = {idx["name"] for idx in inspector.get_indexes("system_metadata")}
        assert "ix_system_metadata_key" in index_names
        assert inspector.get_pk_constraint("system_metadata")["name"] == "pk_system_metadata"
    finally:
        engine.dispose()


def test_models_match_migrations(empty_database: str) -> None:
    """No drift between SQLAlchemy models and migration history.

    `alembic check` exits non-zero when autogenerate would still produce
    changes — i.e. when someone edited a model without writing a migration.
    """
    _run_alembic_ok("upgrade", "head", db_url=empty_database)

    result = _run_alembic("check", db_url=empty_database)

    if result.returncode != 0:
        pytest.fail(
            "SQLAlchemy models and Alembic migrations have diverged. "
            'Generate a migration with `make revision m="..."`.\n'
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )


def test_downgrade_to_base_is_reversible(empty_database: str) -> None:
    """The initial migration can be rolled back cleanly."""
    _run_alembic_ok("upgrade", "head", db_url=empty_database)
    _run_alembic_ok("downgrade", "base", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        assert "system_metadata" not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
