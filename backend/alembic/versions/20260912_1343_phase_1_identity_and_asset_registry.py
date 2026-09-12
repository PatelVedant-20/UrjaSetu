"""phase 1 identity and asset registry

Creates entities 1-9 of docs/04_DATA_MODEL.md: users, utility_accounts,
consents, grid_nodes, sites, meters, energy_assets, inverter_devices and
verification_records.

Two deviations from plain autogenerate output, both deliberate:

1. The native enum types are created and dropped explicitly. `op.create_table`
   would emit `CREATE TYPE` once per table that uses an enum, and
   `verification_level` is used by three tables — the second one would fail
   with "type already exists".
2. `op.drop_table` does not drop enum types. Without the explicit drops in
   `downgrade()`, a downgrade followed by an upgrade fails on the leftover
   types. The Phase 1 migration tests exercise exactly that round trip.

Revision ID: 0002_identity_asset_registry
Revises: 0001_system_metadata
Create Date: 2026-09-12 13:43:35.117755
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_identity_asset_registry"
down_revision: str | None = "0001_system_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Single source of truth for this migration's enum types. `create_type=False`
# stops `op.create_table` from emitting its own CREATE TYPE; the loops in
# upgrade()/downgrade() own the lifecycle instead.
def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


user_role = _enum("user_role", "consumer", "prosumer", "operator", "regulator_viewer", "admin")
user_status = _enum("user_status", "pending", "active", "suspended")
verification_level = _enum(
    "verification_level", "none", "self_declared", "document_verified", "discom_verified"
)
consent_scope = _enum("consent_scope", "meter_data", "device_data", "market_participation")
grid_node_type = _enum("grid_node_type", "substation", "feeder", "transformer", "connection_point")
meter_type = _enum("meter_type", "smart_meter", "net_meter", "gross_meter")
energy_asset_type = _enum("energy_asset_type", "pv", "battery", "ev")
energy_asset_status = _enum(
    "energy_asset_status", "planned", "active", "inactive", "decommissioned"
)
inverter_protocol = _enum(
    "inverter_protocol",
    "sunspec_modbus_tcp",
    "sunspec_modbus_rtu",
    "vendor_api",
    "simulated",
    "unknown",
)
verification_type = _enum(
    "verification_type", "identity", "utility_account", "meter", "energy_asset"
)
verification_source = _enum(
    "verification_source", "self_declared", "discom", "third_party", "operator"
)
verification_status = _enum(
    "verification_status", "pending", "verified", "rejected", "expired", "revoked"
)

ALL_ENUMS = (
    user_role,
    user_status,
    verification_level,
    consent_scope,
    grid_node_type,
    meter_type,
    energy_asset_type,
    energy_asset_status,
    inverter_protocol,
    verification_type,
    verification_source,
    verification_status,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    # --- grid twin -------------------------------------------------------
    op.create_table(
        "grid_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_ref", sa.String(length=128), nullable=False),
        sa.Column("node_type", grid_node_type, nullable=False),
        sa.Column("nominal_voltage_kv", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("parent_node_id", sa.Uuid(), nullable=True),
        sa.Column("feeder_id", sa.String(length=64), nullable=True),
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
            "nominal_voltage_kv > 0", name=op.f("ck_grid_nodes_nominal_voltage_positive")
        ),
        sa.CheckConstraint(
            "parent_node_id IS NULL OR parent_node_id <> id",
            name=op.f("ck_grid_nodes_no_self_parent"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_node_id"],
            ["grid_nodes.id"],
            name=op.f("fk_grid_nodes_parent_node_id_grid_nodes"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grid_nodes")),
        sa.UniqueConstraint("external_ref", name="uq_grid_nodes_external_ref"),
    )
    op.create_index("ix_grid_nodes_feeder_id", "grid_nodes", ["feeder_id"], unique=False)
    op.create_index("ix_grid_nodes_parent_node_id", "grid_nodes", ["parent_node_id"], unique=False)

    # --- identity --------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("status", user_status, server_default="pending", nullable=False),
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
            "length(trim(display_name)) > 0", name=op.f("ck_users_display_name_not_blank")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "utility_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("discom_code", sa.String(length=64), nullable=False),
        sa.Column("consumer_number_hash", sa.String(length=128), nullable=False),
        sa.Column("verification_level", verification_level, server_default="none", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
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
            "verification_level = 'none' OR verified_at IS NOT NULL",
            name=op.f("ck_utility_accounts_verified_at_required_when_verified"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_utility_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_utility_accounts")),
        sa.UniqueConstraint(
            "discom_code",
            "consumer_number_hash",
            name="uq_utility_accounts_discom_code_consumer_number_hash",
        ),
    )
    op.create_index("ix_utility_accounts_user_id", "utility_accounts", ["user_id"], unique=False)

    op.create_table(
        "consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", consent_scope, nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            "revoked_at IS NULL OR revoked_at >= granted_at",
            name=op.f("ck_consents_revoked_after_granted"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_consents_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
    )
    op.create_index("ix_consents_user_id_scope", "consents", ["user_id", "scope"], unique=False)

    # --- sites and site-scoped assets ------------------------------------
    op.create_table(
        "sites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("grid_node_id", sa.Uuid(), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="Asia/Kolkata", nullable=False),
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
            "latitude IS NULL OR latitude BETWEEN -90 AND 90", name=op.f("ck_sites_latitude_range")
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name=op.f("ck_sites_longitude_range"),
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_sites_name_not_blank")),
        sa.ForeignKeyConstraint(
            ["grid_node_id"],
            ["grid_nodes.id"],
            name=op.f("fk_sites_grid_node_id_grid_nodes"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_sites_owner_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sites")),
    )
    op.create_index("ix_sites_grid_node_id", "sites", ["grid_node_id"], unique=False)
    op.create_index("ix_sites_owner_user_id", "sites", ["owner_user_id"], unique=False)

    op.create_table(
        "meters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("meter_type", meter_type, nullable=False),
        sa.Column("vendor", sa.String(length=128), nullable=True),
        sa.Column("external_meter_ref", sa.String(length=128), nullable=True),
        sa.Column("verification_level", verification_level, server_default="none", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["site_id"], ["sites.id"], name=op.f("fk_meters_site_id_sites"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meters")),
        sa.UniqueConstraint("external_meter_ref", name="uq_meters_external_meter_ref"),
    )
    op.create_index("ix_meters_site_id", "meters", ["site_id"], unique=False)

    op.create_table(
        "energy_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("asset_type", energy_asset_type, nullable=False),
        sa.Column("capacity_kw", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", energy_asset_status, server_default="planned", nullable=False),
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
        sa.CheckConstraint("capacity_kw > 0", name=op.f("ck_energy_assets_capacity_positive")),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["sites.id"],
            name=op.f("fk_energy_assets_site_id_sites"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_energy_assets")),
    )
    op.create_index("ix_energy_assets_site_id", "energy_assets", ["site_id"], unique=False)
    op.create_index(
        "ix_energy_assets_site_id_asset_type",
        "energy_assets",
        ["site_id", "asset_type"],
        unique=False,
    )

    op.create_table(
        "inverter_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("energy_asset_id", sa.Uuid(), nullable=False),
        sa.Column("manufacturer", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("protocol", inverter_protocol, server_default="unknown", nullable=False),
        sa.Column("external_device_ref", sa.String(length=128), nullable=True),
        sa.Column("adapter_type", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["energy_asset_id"],
            ["energy_assets.id"],
            name=op.f("fk_inverter_devices_energy_asset_id_energy_assets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inverter_devices")),
        sa.UniqueConstraint("external_device_ref", name="uq_inverter_devices_external_device_ref"),
    )
    op.create_index(
        "ix_inverter_devices_energy_asset_id", "inverter_devices", ["energy_asset_id"], unique=False
    )

    # --- verification ----------------------------------------------------
    op.create_table(
        "verification_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("verification_type", verification_type, nullable=False),
        sa.Column("source", verification_source, nullable=False),
        sa.Column("verification_level", verification_level, server_default="none", nullable=False),
        sa.Column("status", verification_status, server_default="pending", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
            "expires_at IS NULL OR verified_at IS NULL OR expires_at > verified_at",
            name=op.f("ck_verification_records_expires_after_verified"),
        ),
        sa.CheckConstraint(
            "status <> 'verified' OR verified_at IS NOT NULL",
            name=op.f("ck_verification_records_verified_at_required_when_verified"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["energy_assets.id"],
            name=op.f("fk_verification_records_asset_id_energy_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_verification_records_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_records")),
    )
    op.create_index(
        "ix_verification_records_asset_id", "verification_records", ["asset_id"], unique=False
    )
    op.create_index(
        "ix_verification_records_user_id", "verification_records", ["user_id"], unique=False
    )
    op.create_index(
        "ix_verification_records_user_id_verification_type_status",
        "verification_records",
        ["user_id", "verification_type", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verification_records_user_id_verification_type_status",
        table_name="verification_records",
    )
    op.drop_index("ix_verification_records_user_id", table_name="verification_records")
    op.drop_index("ix_verification_records_asset_id", table_name="verification_records")
    op.drop_table("verification_records")

    op.drop_index("ix_inverter_devices_energy_asset_id", table_name="inverter_devices")
    op.drop_table("inverter_devices")

    op.drop_index("ix_energy_assets_site_id_asset_type", table_name="energy_assets")
    op.drop_index("ix_energy_assets_site_id", table_name="energy_assets")
    op.drop_table("energy_assets")

    op.drop_index("ix_meters_site_id", table_name="meters")
    op.drop_table("meters")

    op.drop_index("ix_sites_owner_user_id", table_name="sites")
    op.drop_index("ix_sites_grid_node_id", table_name="sites")
    op.drop_table("sites")

    op.drop_index("ix_consents_user_id_scope", table_name="consents")
    op.drop_table("consents")

    op.drop_index("ix_utility_accounts_user_id", table_name="utility_accounts")
    op.drop_table("utility_accounts")

    op.drop_table("users")

    op.drop_index("ix_grid_nodes_parent_node_id", table_name="grid_nodes")
    op.drop_index("ix_grid_nodes_feeder_id", table_name="grid_nodes")
    op.drop_table("grid_nodes")

    # Tables are gone; the types they used are not. Drop them last, after every
    # column that referenced them has been removed.
    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
