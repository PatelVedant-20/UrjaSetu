"""phase 2 telemetry readings

Creates entity 10 of docs/04_DATA_MODEL.md: `telemetry_readings`, the
normalized measurement store.

As in migration 0002, the native enum types are created and dropped explicitly.
`op.create_table` would emit its own CREATE TYPE, and `op.drop_table` never
drops the types at all — without the explicit drops below, a downgrade followed
by an upgrade fails on the leftover types. The Phase 2 migration tests exercise
exactly that round trip.

Revision ID: 0003_telemetry_readings
Revises: 0002_identity_asset_registry
Create Date: 2026-09-12 15:02:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_telemetry_readings"
down_revision: str | None = "0002_identity_asset_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


telemetry_quality_status = _enum(
    "telemetry_quality_status",
    "valid",
    "missing",
    "stale",
    "out_of_order",
    "duplicate",
    "invalid_value",
    "source_unavailable",
)
telemetry_source = _enum("telemetry_source", "meter", "inverter", "simulator", "import", "manual")

ALL_ENUMS = (telemetry_quality_status, telemetry_source)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "telemetry_readings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meter_id", sa.Uuid(), nullable=False),
        sa.Column("energy_asset_id", sa.Uuid(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        # NULL means "this device does not measure this channel", which is
        # deliberately distinct from a measured zero.
        sa.Column("generation_kw", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("load_kw", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("grid_import_kw", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("grid_export_kw", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("energy_kwh", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("battery_soc", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column(
            "quality_status", telemetry_quality_status, server_default="valid", nullable=False
        ),
        sa.Column("source", telemetry_source, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "interval_end >= interval_start",
            name=op.f("ck_telemetry_readings_interval_end_not_before_start"),
        ),
        sa.CheckConstraint(
            "generation_kw IS NULL OR generation_kw >= 0",
            name=op.f("ck_telemetry_readings_generation_kw_not_negative"),
        ),
        sa.CheckConstraint(
            "load_kw IS NULL OR load_kw >= 0",
            name=op.f("ck_telemetry_readings_load_kw_not_negative"),
        ),
        sa.CheckConstraint(
            "grid_import_kw IS NULL OR grid_import_kw >= 0",
            name=op.f("ck_telemetry_readings_grid_import_kw_not_negative"),
        ),
        sa.CheckConstraint(
            "grid_export_kw IS NULL OR grid_export_kw >= 0",
            name=op.f("ck_telemetry_readings_grid_export_kw_not_negative"),
        ),
        sa.CheckConstraint(
            "energy_kwh IS NULL OR energy_kwh >= 0",
            name=op.f("ck_telemetry_readings_energy_kwh_not_negative"),
        ),
        sa.CheckConstraint(
            "battery_soc IS NULL OR battery_soc BETWEEN 0 AND 100",
            name=op.f("ck_telemetry_readings_battery_soc_percent"),
        ),
        sa.ForeignKeyConstraint(
            ["energy_asset_id"],
            ["energy_assets.id"],
            name=op.f("fk_telemetry_readings_energy_asset_id_energy_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["meter_id"],
            ["meters.id"],
            name=op.f("fk_telemetry_readings_meter_id_meters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_telemetry_readings")),
        # NULLS NOT DISTINCT (PostgreSQL 15+) is required: by default every NULL
        # energy_asset_id would be treated as unique, letting whole-site
        # readings be inserted twice for the same interval and double-count
        # energy at settlement.
        sa.UniqueConstraint(
            "meter_id",
            "energy_asset_id",
            "interval_start",
            name="uq_telemetry_readings_meter_id_energy_asset_id_interval_start",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_telemetry_readings_energy_asset_id",
        "telemetry_readings",
        ["energy_asset_id"],
        unique=False,
    )
    op.create_index(
        "ix_telemetry_readings_meter_id_interval_start",
        "telemetry_readings",
        ["meter_id", "interval_start"],
        unique=False,
    )
    op.create_index(
        "ix_telemetry_readings_meter_id_quality_status_interval_start",
        "telemetry_readings",
        ["meter_id", "quality_status", "interval_start"],
        unique=False,
    )
    op.create_index(
        "ix_telemetry_readings_meter_id_timestamp",
        "telemetry_readings",
        ["meter_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_readings_meter_id_timestamp", table_name="telemetry_readings")
    op.drop_index(
        "ix_telemetry_readings_meter_id_quality_status_interval_start",
        table_name="telemetry_readings",
    )
    op.drop_index("ix_telemetry_readings_meter_id_interval_start", table_name="telemetry_readings")
    op.drop_index("ix_telemetry_readings_energy_asset_id", table_name="telemetry_readings")
    op.drop_table("telemetry_readings")

    # The table is gone; the types it used are not.
    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
