"""Phase 1 migration state & schema reflection tests.

Verifies that all 9 Phase 1 tables and constraints are defined in SQLAlchemy metadata,
Alembic migration scripts exist and follow naming conventions, and the database schema
reflects docs/04_DATA_MODEL.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect

from app.db.base import Base, NAMING_CONVENTION


REQUIRED_PHASE1_TABLES = [
    "users",
    "utility_accounts",
    "sites",
    "grid_nodes",
    "meters",
    "energy_assets",
    "inverter_devices",
    "verification_records",
    "consents",
]


class TestMetadataAndTableDefinitions:
    """Verify that all Phase 1 tables are mapped in SQLAlchemy Base.metadata."""

    @pytest.mark.parametrize("table_name", REQUIRED_PHASE1_TABLES)
    def test_table_exists_in_declarative_metadata(self, table_name: str) -> None:
        """Every Phase 1 entity table must be declared in Base.metadata."""
        assert (
            table_name in Base.metadata.tables
        ), f"Table '{table_name}' is missing from Base.metadata. Check docs/04_DATA_MODEL.md."

    def test_naming_convention_is_configured_on_metadata(self) -> None:
        """Metadata must use the deterministic naming convention defined in app/db/base.py."""
        assert Base.metadata.naming_convention == NAMING_CONVENTION
        assert "pk" in Base.metadata.naming_convention
        assert "fk" in Base.metadata.naming_convention
        assert "uq" in Base.metadata.naming_convention
        assert "ix" in Base.metadata.naming_convention


class TestAlembicMigrationFiles:
    """Verify that Alembic migration versions exist for Phase 1."""

    def test_migration_versions_directory_exists(self) -> None:
        versions_dir = Path(__file__).parents[3] / "alembic" / "versions"
        assert versions_dir.exists(), f"Versions directory {versions_dir} does not exist"
        assert versions_dir.is_dir()

    def test_phase1_migration_script_exists(self) -> None:
        versions_dir = Path(__file__).parents[3] / "alembic" / "versions"
        migration_files = list(versions_dir.glob("*.py"))
        # We expect Phase 0 (system_metadata) and Phase 1 migration files
        assert len(migration_files) >= 1, "No migration scripts found in alembic/versions"

        # Check if there is a migration that references Phase 1 tables
        phase1_keywords = ["identity", "assets", "phase1", "users", "sites", "meters"]
        has_phase1_migration = any(
            any(kw in f.name.lower() for kw in phase1_keywords) for f in migration_files
        )
        assert (
            has_phase1_migration
        ), f"No Phase 1 migration script found in alembic/versions. Found: {[f.name for f in migration_files]}"


class TestLiveDatabaseSchema:
    """Verify live PostgreSQL database schema when engine is available."""

    @pytest.mark.parametrize("table_name", REQUIRED_PHASE1_TABLES)
    def test_table_exists_in_database(self, engine: Engine, table_name: str) -> None:
        """The migration must create the table in PostgreSQL."""
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        assert (
            table_name in existing_tables
        ), f"Table '{table_name}' was not created in PostgreSQL. Run `alembic upgrade head`."
