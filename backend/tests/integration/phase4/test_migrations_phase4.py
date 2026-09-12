"""Phase 4: migration verification.

Runs against a throwaway database migrated from empty. The downgrade/upgrade
round trip is the case that matters: `op.drop_table` does not drop PostgreSQL
enum types, so a migration that forgets them passes once and fails the second
time it is applied.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import run_alembic, run_alembic_ok

PHASE_3_REVISION = "0004_forecast_runs_and_points"
PHASE_4_REVISION = "0005_market_orders_trades"

PHASE_4_TABLES = {"market_sessions", "orders", "trades"}
PHASE_4_ENUM_TYPES = {
    "market_type",
    "market_session_status",
    "order_side",
    "order_status",
    "trade_status",
}


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


def test_revision_id_fits_the_alembic_version_column() -> None:
    """`alembic_version.version_num` is varchar(32).

    A longer id applies the migration and then fails to stamp it, leaving the
    database silently one revision behind.
    """
    assert len(PHASE_4_REVISION) <= 32


def test_upgrade_creates_the_market_tables(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_4_TABLES.issubset(_tables(empty_database))


def test_upgrade_creates_the_market_enum_types(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_4_ENUM_TYPES.issubset(_enum_types(empty_database))


def test_upgrading_to_the_phase_4_revision_lands_there(empty_database: str) -> None:
    """Phase-local by design: asserting against `head` would break in Phase 5."""
    run_alembic_ok("upgrade", PHASE_4_REVISION, db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()

    assert current == PHASE_4_REVISION


def test_models_match_migrations(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    result = run_alembic("check", db_url=empty_database)

    if result.returncode != 0:
        pytest.fail(
            "SQLAlchemy models and Alembic migrations have diverged.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )


def test_orders_carry_the_side_specific_price_constraints(empty_database: str) -> None:
    """The rules docs/04_DATA_MODEL.md entity 14 lists must live in the schema."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        names = {c["name"] for c in inspect(engine).get_check_constraints("orders")}
    finally:
        engine.dispose()

    assert "ck_orders_buy_requires_max_price" in names
    assert "ck_orders_sell_requires_min_price" in names


def test_downgrade_removes_phase_4_and_leaves_phase_3_intact(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_3_REVISION, db_url=empty_database)

    tables = _tables(empty_database)
    assert not (PHASE_4_TABLES & tables)
    assert {"forecast_runs", "forecast_points", "telemetry_readings", "users"}.issubset(tables)


def test_downgrade_also_drops_the_market_enum_types(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_3_REVISION, db_url=empty_database)

    leftover = PHASE_4_ENUM_TYPES & _enum_types(empty_database)
    assert not leftover, f"enum types survived the downgrade: {sorted(leftover)}"


def test_upgrade_downgrade_upgrade_round_trip(empty_database: str) -> None:
    """The exact sequence the Phase 4 brief requires."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_3_REVISION, db_url=empty_database)
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_4_TABLES.issubset(_tables(empty_database))
    assert PHASE_4_ENUM_TYPES.issubset(_enum_types(empty_database))
    assert run_alembic("check", db_url=empty_database).returncode == 0


def test_full_downgrade_to_base_and_back(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", "base", db_url=empty_database)

    assert not (PHASE_4_TABLES & _tables(empty_database))

    run_alembic_ok("upgrade", "head", db_url=empty_database)
    assert PHASE_4_TABLES.issubset(_tables(empty_database))
