"""Phase 3: migration verification.

Runs against a throwaway database migrated from empty. The downgrade/upgrade
round trip is the case that matters: `op.drop_table` does not drop PostgreSQL
enum types, so a migration that forgets them passes once and fails the second
time it is applied.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import run_alembic, run_alembic_ok

PHASE_2_REVISION = "0003_telemetry_readings"
PHASE_3_REVISION = "0004_forecast_runs_and_points"

PHASE_3_TABLES = {"forecast_runs", "forecast_points"}
PHASE_3_ENUM_TYPES = {"forecast_type", "forecast_run_status"}


def _tables(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _enum_types(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as connection:
            return set(
                connection.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'"))
                .scalars()
                .all()
            )
    finally:
        engine.dispose()


def test_upgrade_creates_the_forecast_tables(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_3_TABLES.issubset(_tables(empty_database))


def test_upgrade_creates_the_forecast_enum_types(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_3_ENUM_TYPES.issubset(_enum_types(empty_database))


def test_upgrading_to_the_phase_3_revision_lands_there(empty_database: str) -> None:
    """Upgrading *to this revision* stamps it.

    Phase-local by design: asserting against `head` would break as soon as
    Phase 4 adds a migration, which says nothing about this one.
    """
    run_alembic_ok("upgrade", PHASE_3_REVISION, db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()

    assert current == PHASE_3_REVISION


def test_models_match_migrations(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    result = run_alembic("check", db_url=empty_database)

    if result.returncode != 0:
        pytest.fail(
            "SQLAlchemy models and Alembic migrations have diverged.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )


def test_forecast_points_have_the_expected_columns(empty_database: str) -> None:
    """Exactly docs/04_DATA_MODEL.md entity 12, plus the shared conventions."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("forecast_points")}
    finally:
        engine.dispose()

    assert columns == {
        "id",
        "forecast_run_id",
        "site_id",
        "interval_start",
        "interval_end",
        "predicted_kw",
        "predicted_kwh",
        "confidence",
        "lower_bound",
        "upper_bound",
        "created_at",
        "updated_at",
    }


def test_downgrade_removes_phase_3_and_leaves_phase_2_intact(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_2_REVISION, db_url=empty_database)

    tables = _tables(empty_database)
    assert not (PHASE_3_TABLES & tables)
    assert "telemetry_readings" in tables
    assert {"users", "sites", "meters"}.issubset(tables)


def test_downgrade_also_drops_the_forecast_enum_types(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_2_REVISION, db_url=empty_database)

    leftover = PHASE_3_ENUM_TYPES & _enum_types(empty_database)
    assert not leftover, f"enum types survived the downgrade: {sorted(leftover)}"


def test_upgrade_downgrade_upgrade_round_trip(empty_database: str) -> None:
    """The exact sequence the Phase 3 brief requires."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_2_REVISION, db_url=empty_database)
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_3_TABLES.issubset(_tables(empty_database))
    assert PHASE_3_ENUM_TYPES.issubset(_enum_types(empty_database))
    assert run_alembic("check", db_url=empty_database).returncode == 0


def test_full_downgrade_to_base_and_back(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", "base", db_url=empty_database)

    assert not (PHASE_3_TABLES & _tables(empty_database))

    run_alembic_ok("upgrade", "head", db_url=empty_database)
    assert PHASE_3_TABLES.issubset(_tables(empty_database))
