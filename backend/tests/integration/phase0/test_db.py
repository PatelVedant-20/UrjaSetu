"""Phase 0 gate: PostgreSQL connectivity and a real ORM read/write.

This is the test that proves the database is *verified*, not merely configured.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import SystemMetadata


def test_engine_is_postgresql(engine: Engine) -> None:
    """Guard against a silent swap to SQLite or another backend."""
    assert engine.dialect.name == "postgresql"


def test_server_version_is_postgresql_18_or_newer(engine: Engine) -> None:
    """docs/02_TECH_STACK.md pins PostgreSQL 18.x."""
    with engine.connect() as connection:
        version = connection.execute(text("SHOW server_version")).scalar_one()

    major = int(str(version).split(".")[0])
    assert major >= 18, f"Expected PostgreSQL 18.x or newer, found {version}"


def test_select_one_executes(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_settings_reject_non_postgresql_urls() -> None:
    """Configuration refuses SQLite outright rather than degrading quietly."""
    with pytest.raises(ValueError, match="requires PostgreSQL"):
        Settings(database_url="sqlite:///./urjasetu.db")


def test_settings_redact_the_password() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:secret@localhost:5432/urjasetu")

    assert "secret" not in settings.safe_database_url()
    assert settings.safe_database_url().endswith("@localhost:5432/urjasetu")


def test_system_metadata_table_exists(engine: Engine) -> None:
    """The migration has been applied to the database under test."""
    tables = inspect(engine).get_table_names()

    assert "system_metadata" in tables, "Run `make migrate` before the test suite."
    assert "alembic_version" in tables


def test_orm_write_then_read(db_session: Session) -> None:
    """The Phase 0 gate's ORM round-trip.

    Writes through SQLAlchemy, flushes to PostgreSQL, reads back, and confirms
    the server-side conventions from app/db/base.py were applied.
    """
    key = f"phase0.check.{uuid.uuid4()}"
    db_session.add(SystemMetadata(key=key, value="ok"))
    db_session.flush()

    stored = db_session.query(SystemMetadata).filter_by(key=key).one()

    assert stored.value == "ok"
    assert isinstance(stored.id, uuid.UUID)
    # Timestamps come from the database default, and are timezone-aware UTC
    # per docs/00_PROJECT_BIBLE.md section 6.
    assert stored.created_at is not None
    assert stored.created_at.tzinfo is not None
    assert stored.updated_at is not None


def test_unique_key_constraint_is_enforced(db_session: Session) -> None:
    """Constraints live in the database, not only in application code."""
    key = f"phase0.unique.{uuid.uuid4()}"
    db_session.add(SystemMetadata(key=key, value="first"))
    db_session.flush()

    db_session.add(SystemMetadata(key=key, value="second"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_db_session_rolls_back_between_tests(engine: Engine) -> None:
    """Rows written by the fixture-scoped tests above did not persist."""
    with engine.connect() as connection:
        leftover = connection.execute(
            text("SELECT count(*) FROM system_metadata WHERE key LIKE 'phase0.%'")
        ).scalar_one()

    assert leftover == 0
