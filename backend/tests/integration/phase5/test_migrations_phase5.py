"""Phase 5: migration verification.

Runs against a throwaway database migrated from empty. The downgrade/upgrade
round trip is the case that matters: `op.drop_table` does not drop PostgreSQL
enum types, so a migration that forgets them passes once and fails the second
time it is applied.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.conftest import run_alembic, run_alembic_ok

PHASE_4_REVISION = "0005_market_orders_trades"
PHASE_5_REVISION = "0006_grid_validation"
CAPACITY_REVISION = "0007_grid_capacity_ratings"
TRADE_FK_REVISION = "0008_trade_grid_validation_fk"

# Every revision in the Phase 5 set, each of which has to fit the version column.
PHASE_5_REVISIONS = (PHASE_5_REVISION, CAPACITY_REVISION, TRADE_FK_REVISION)

PHASE_5_TABLES = {"grid_snapshots", "grid_validation_runs"}
PHASE_5_ENUM_TYPES = {"grid_validation_decision", "grid_validation_status"}

# docs/00_PROJECT_BIBLE.md section 4. Stored as lowercase values rather than
# member names, which is what `pg_enum`'s values_callable arranges.
DECISION_VALUES = {"accept", "reprice", "reduce", "shift", "reject"}
# Three states, so a failed or unassessable validation is never recorded as safe.
STATUS_VALUES = {"safe", "unsafe", "unknown"}

TRADE_FK = "fk_trades_grid_validation_id_grid_validation_runs"


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


@pytest.mark.parametrize("revision", PHASE_5_REVISIONS)
def test_revision_id_fits_the_alembic_version_column(revision: str) -> None:
    """`alembic_version.version_num` is varchar(32).

    A longer id applies the migration and then fails to stamp it, leaving the
    database silently one revision behind — which has happened here before.
    """
    assert len(revision) <= 32


def test_upgrade_creates_the_grid_tables(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_5_TABLES.issubset(_tables(empty_database))


def test_upgrade_creates_the_decision_enum_with_the_documented_values(
    empty_database: str,
) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_5_ENUM_TYPES.issubset(_enum_types(empty_database))

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            stored = set(
                connection.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'grid_validation_decision'"
                    )
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert stored == DECISION_VALUES


def test_upgrade_creates_the_status_enum_with_all_three_states(empty_database: str) -> None:
    """Two states would force a solver failure to be recorded as one of them."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            stored = set(
                connection.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = 'grid_validation_status'"
                    )
                )
                .scalars()
                .all()
            )
    finally:
        engine.dispose()

    assert stored == STATUS_VALUES


def test_upgrading_to_the_phase_5_revision_lands_there(empty_database: str) -> None:
    """Phase-local by design: asserting against `head` would break in Phase 6."""
    run_alembic_ok("upgrade", PHASE_5_REVISION, db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        with engine.connect() as connection:
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()

    assert current == PHASE_5_REVISION


def test_models_match_migrations(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    result = run_alembic("check", db_url=empty_database)

    if result.returncode != 0:
        pytest.fail(
            "SQLAlchemy models and Alembic migrations have diverged.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            pytrace=False,
        )


def test_validation_runs_carry_the_safety_agreement_constraint(empty_database: str) -> None:
    """The rule that keeps `safe` and `decision` from drifting apart."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        names = {c["name"] for c in inspect(engine).get_check_constraints("grid_validation_runs")}
    finally:
        engine.dispose()

    assert "ck_grid_validation_runs_decision_agrees_with_safety" in names
    assert "ck_grid_validation_runs_voltage_range_ordered" in names


def test_snapshot_measures_are_all_nullable(empty_database: str) -> None:
    """NULL means "not observed"; it must never be forced to zero."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("grid_snapshots")}
    finally:
        engine.dispose()

    for measure in (
        "system_load_kw",
        "generation_kw",
        "transformer_loading_pct",
        "max_line_loading_pct",
        "min_voltage_pu",
        "max_voltage_pu",
    ):
        assert columns[measure]["nullable"] is True, f"{measure} must accept 'not observed'"
    assert columns["captured_at"]["nullable"] is False


def test_a_validation_run_survives_deletion_of_its_snapshot(empty_database: str) -> None:
    """SET NULL, not CASCADE: the judgement outlives the observation."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        keys = inspect(engine).get_foreign_keys("grid_validation_runs")
    finally:
        engine.dispose()

    snapshot_fk = next(k for k in keys if k["referred_table"] == "grid_snapshots")
    assert snapshot_fk["options"]["ondelete"] == "SET NULL"


def test_capacity_column_is_added_to_the_existing_twin(empty_database: str) -> None:
    """`grid_nodes` is extended, not shadowed by a second topology table."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        inspector = inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("grid_nodes")}
        checks = {c["name"] for c in inspector.get_check_constraints("grid_nodes")}
        tables = set(inspector.get_table_names())
    finally:
        engine.dispose()

    assert columns["rated_capacity_kw"]["nullable"] is True
    assert "ck_grid_nodes_rated_capacity_positive" in checks
    assert (
        not {"grid_lines", "grid_edges", "grid_equipment"} & tables
    ), "capacity must extend the existing twin, not introduce a parallel topology"


def test_existing_nodes_are_left_unrated_rather_than_backfilled(empty_database: str) -> None:
    """A default rating would be an invented denominator.

    Every loading percentage derived from one would be fiction presented as
    measurement, so the column arrives NULL and stays NULL until real ratings
    are recorded.
    """
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        columns = {c["name"]: c for c in inspect(engine).get_columns("grid_nodes")}
    finally:
        engine.dispose()

    assert columns["rated_capacity_kw"]["default"] is None


def test_trades_reference_grid_validation_runs(empty_database: str) -> None:
    """The column existed since the market migration; now it has a target."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        keys = inspect(engine).get_foreign_keys("trades")
    finally:
        engine.dispose()

    validation_fk = next(k for k in keys if k["referred_table"] == "grid_validation_runs")
    assert validation_fk["constrained_columns"] == ["grid_validation_id"]
    assert validation_fk["options"]["ondelete"] == "RESTRICT"
    # Exactly the project naming convention, not a doubled prefix.
    assert validation_fk["name"] == TRADE_FK


def test_the_trade_link_is_constrained_in_one_direction_only(empty_database: str) -> None:
    """Constraining both would make the two tables mutually uninsertable."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        keys = inspect(engine).get_foreign_keys("grid_validation_runs")
    finally:
        engine.dispose()

    assert all(k["referred_table"] != "trades" for k in keys)


def test_the_merged_market_migration_is_untouched() -> None:
    """Phase 4's migration must keep the schema it shipped.

    The foreign key is added by an ALTER in a new Phase 5 revision, never by
    editing a revision that is already on main.
    """
    market = Path(
        "backend/alembic/versions/20260912_1718_phase_4_market_sessions_orders_trades.py"
    ).read_text()

    assert "grid_validation_runs" not in market
    assert TRADE_FK not in market


def test_downgrade_of_the_trade_fk_leaves_the_column(empty_database: str) -> None:
    """Reverting the constraint must not drop market data."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", CAPACITY_REVISION, db_url=empty_database)

    engine = create_engine(empty_database)
    try:
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("trades")}
        keys = inspector.get_foreign_keys("trades")
    finally:
        engine.dispose()

    assert "grid_validation_id" in columns
    assert all(k["referred_table"] != "grid_validation_runs" for k in keys)


def test_downgrade_removes_phase_5_and_leaves_phase_4_intact(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_4_REVISION, db_url=empty_database)

    tables = _tables(empty_database)
    assert not (PHASE_5_TABLES & tables)
    assert {"trades", "orders", "market_sessions", "grid_nodes", "users"}.issubset(tables)


def test_downgrade_also_drops_the_grid_enum_type(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_4_REVISION, db_url=empty_database)

    leftover = PHASE_5_ENUM_TYPES & _enum_types(empty_database)
    assert not leftover, f"enum types survived the downgrade: {sorted(leftover)}"


def test_upgrade_downgrade_upgrade_round_trip(empty_database: str) -> None:
    """The exact sequence the Phase 5 brief requires."""
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", PHASE_4_REVISION, db_url=empty_database)
    run_alembic_ok("upgrade", "head", db_url=empty_database)

    assert PHASE_5_TABLES.issubset(_tables(empty_database))
    assert PHASE_5_ENUM_TYPES.issubset(_enum_types(empty_database))
    assert run_alembic("check", db_url=empty_database).returncode == 0


def test_full_downgrade_to_base_and_back(empty_database: str) -> None:
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    run_alembic_ok("downgrade", "base", db_url=empty_database)

    assert not (PHASE_5_TABLES & _tables(empty_database))

    run_alembic_ok("upgrade", "head", db_url=empty_database)
    assert PHASE_5_TABLES.issubset(_tables(empty_database))
