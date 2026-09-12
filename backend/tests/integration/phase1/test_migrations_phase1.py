"""Phase 1: migration verification.

Every assertion runs against a throwaway database migrated from empty, because
running migrations where the schema already exists proves nothing
(docs/10_TESTING_AND_INTEGRATION.md).

The downgrade/upgrade round trip is the test that matters most here: dropping
tables does not drop PostgreSQL enum types, so a migration that forgets them
passes `upgrade` and fails the second time it is applied.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import run_alembic, run_alembic_ok

PHASE_0_REVISION = "0001_system_metadata"
PHASE_1_REVISION = "0002_identity_asset_registry"

PHASE_1_TABLES = {
    "users",
    "utility_accounts",
    "consents",
    "grid_nodes",
    "sites",
    "meters",
    "energy_assets",
    "inverter_devices",
    "verification_records",
}

PHASE_1_ENUM_TYPES = {
    "user_role",
    "user_status",
    "verification_level",
    "consent_scope",
    "grid_node_type",
    "meter_type",
    "energy_asset_type",
    "energy_asset_status",
    "inverter_protocol",
    "verification_type",
    "verification_source",
    "verification_status",
}


def _table_names(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _enum_type_names(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT typname FROM pg_type WHERE typtype = 'e'")
            ).scalars()
            return set(rows)
    finally:
        engine.dispose()


def test_upgrade_head_creates_every_phase_1_table(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_1_TABLES.issubset(_table_names(empty_database))


def test_upgrade_head_creates_every_enum_type(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_1_ENUM_TYPES.issubset(_enum_type_names(empty_database))


def test_models_match_migrations(empty_database: str) -> None:
    """`alembic check` exits non-zero if autogenerate would still emit changes."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    result = run_alembic("check", db_url=empty_database)

    if result.returncode != 0:
        pytest.fail(
            "SQLAlchemy models and Alembic migrations have diverged. "
            'Generate a migration with `make revision m="..."`.\n'
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )


def test_downgrade_to_phase_0_removes_phase_1_schema(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_0_REVISION, db_url=empty_database)

    tables = _table_names(empty_database)
    assert not (PHASE_1_TABLES & tables), "Phase 1 tables survived the downgrade"
    # Phase 0 is untouched.
    assert "system_metadata" in tables
    assert "alembic_version" in tables


def test_downgrade_also_drops_the_enum_types(empty_database: str) -> None:
    """`op.drop_table` leaves enum types behind; the migration must drop them."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_0_REVISION, db_url=empty_database)

    leftover = PHASE_1_ENUM_TYPES & _enum_type_names(empty_database)
    assert not leftover, f"enum types survived the downgrade: {sorted(leftover)}"


def test_upgrade_downgrade_upgrade_round_trip(empty_database: str) -> None:
    """The sequence a reviewer runs by hand, and the one that catches leftovers."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_0_REVISION, db_url=empty_database)
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_1_TABLES.issubset(_table_names(empty_database))
    assert PHASE_1_ENUM_TYPES.issubset(_enum_type_names(empty_database))


def test_upgrading_to_the_phase_1_revision_lands_there(empty_database: str) -> None:
    """Upgrading *to this revision* stamps it.

    Deliberately not asserted against `head`: head advances with every later
    phase, and this test is about Phase 1's migration, not about which
    migration happens to be newest.
    """
    run_alembic_ok("upgrade", PHASE_1_REVISION, db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()

    assert current == PHASE_1_REVISION


def test_downgrade_to_base_is_fully_reversible(empty_database: str) -> None:
    """All the way down and back up, exercising both migrations together."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", "base", db_url=empty_database)

    assert not (PHASE_1_TABLES & _table_names(empty_database))
    assert "system_metadata" not in _table_names(empty_database)

    run_alembic_ok("upgrade", "head", db_url=empty_database)
    tables = _table_names(empty_database)
    assert PHASE_1_TABLES.issubset(tables)
    assert "system_metadata" in tables
