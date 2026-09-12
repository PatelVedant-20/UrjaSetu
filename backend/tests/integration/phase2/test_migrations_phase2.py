"""Phase 2: migration verification.

Runs against a throwaway database migrated from empty. The downgrade/upgrade
round trip is the case that matters: `op.drop_table` does not drop PostgreSQL
enum types, so a migration that forgets them passes once and fails the second
time it is applied.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import run_alembic, run_alembic_ok

PHASE_1_REVISION = "0002_identity_asset_registry"
PHASE_2_REVISION = "0003_telemetry_readings"

PHASE_2_ENUM_TYPES = {"telemetry_quality_status", "telemetry_source"}


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


def test_upgrade_head_creates_the_telemetry_table(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert "telemetry_readings" in _tables(empty_database)


def test_upgrade_head_creates_the_telemetry_enum_types(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_2_ENUM_TYPES.issubset(_enum_types(empty_database))


def test_head_is_the_phase_2_revision(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()

    assert current == PHASE_2_REVISION


def test_models_match_migrations(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    result = run_alembic("check", db_url=empty_database)

    if result.returncode != 0:
        pytest.fail(
            "SQLAlchemy models and Alembic migrations have diverged.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )


def test_natural_key_uses_nulls_not_distinct(empty_database: str) -> None:
    """Without NULLS NOT DISTINCT, whole-site readings could double-count.

    PostgreSQL records this on the index, so it is asserted against the live
    schema rather than against the model.
    """
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            nulls_not_distinct = connection.execute(
                text(
                    "SELECT indnullsnotdistinct FROM pg_index "
                    "WHERE indexrelid = 'uq_telemetry_readings_meter_id_"
                    "energy_asset_id_interval_start'::regclass"
                )
            ).scalar_one()
    finally:
        engine.dispose()

    assert nulls_not_distinct is True


def test_downgrade_removes_the_table_and_leaves_phase_1_intact(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_1_REVISION, db_url=empty_database)

    tables = _tables(empty_database)
    assert "telemetry_readings" not in tables
    # Phase 1 is untouched.
    assert {"users", "sites", "meters", "energy_assets"}.issubset(tables)


def test_downgrade_also_drops_the_telemetry_enum_types(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_1_REVISION, db_url=empty_database)

    leftover = PHASE_2_ENUM_TYPES & _enum_types(empty_database)
    assert not leftover, f"enum types survived the downgrade: {sorted(leftover)}"


def test_upgrade_downgrade_upgrade_round_trip(empty_database: str) -> None:
    """The exact sequence the Phase 2 brief requires."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_1_REVISION, db_url=empty_database)
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert "telemetry_readings" in _tables(empty_database)
    assert PHASE_2_ENUM_TYPES.issubset(_enum_types(empty_database))

    result = run_alembic("check", db_url=empty_database)
    assert result.returncode == 0, result.stdout + result.stderr


def test_full_downgrade_to_base_and_back(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", "base", db_url=empty_database)

    assert "telemetry_readings" not in _tables(empty_database)

    run_alembic_ok("upgrade", "head", db_url=empty_database)
    assert "telemetry_readings" in _tables(empty_database)
