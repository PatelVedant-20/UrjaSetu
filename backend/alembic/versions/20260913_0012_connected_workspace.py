"""Connected marketplace: measured channels, sessions and durable receipts."""

import sqlalchemy as sa

from alembic import op

revision = "0012_connected_workspace"
down_revision = "0011_audit_events"
branch_labels = None
depends_on = None


def upgrade():
    for value in ("committed", "rejected", "settled"):
        op.execute(f"ALTER TYPE trade_status ADD VALUE IF NOT EXISTS '{value}'")
    for name in ("generation_kwh", "load_kwh", "grid_import_kwh", "grid_export_kwh"):
        op.add_column("telemetry_readings", sa.Column(name, sa.Numeric(14, 4), nullable=True))
    # Explicit frozen DDL for new tables, independent of future ORM changes.
    op.create_table(
        "login_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    from sqlalchemy.dialects.postgresql import JSONB

    op.create_table(
        "simulation_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clock", sa.DateTime(timezone=True), nullable=False),
        sa.Column("running", sa.Boolean(), nullable=False),
        sa.Column("scenario", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("weather", JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "trade_allocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("trade_id", sa.Uuid(), sa.ForeignKey("trades.id"), nullable=False, unique=True),
        sa.Column(
            "seller_reading_id", sa.Uuid(), sa.ForeignKey("telemetry_readings.id"), nullable=False
        ),
        sa.Column(
            "buyer_reading_id", sa.Uuid(), sa.ForeignKey("telemetry_readings.id"), nullable=False
        ),
        sa.Column("energy_kwh", sa.Numeric(14, 4), nullable=False),
    )
    op.create_table(
        "blockchain_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("trade_id", sa.Uuid(), sa.ForeignKey("trades.id"), nullable=False, unique=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("transaction_hash", sa.String(66)),
        sa.Column("block_number", sa.Integer()),
        sa.Column("chain_id", sa.Integer()),
        sa.Column("contract_address", sa.String(42)),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("settlement_id", sa.Uuid(), sa.ForeignKey("settlements.id"), nullable=False),
        sa.Column("account", sa.String(100), nullable=False),
        sa.Column("amount_inr", sa.Numeric(16, 2), nullable=False),
        sa.UniqueConstraint("settlement_id", "account"),
    )


def downgrade():
    for name in (
        "journal_entries",
        "blockchain_receipts",
        "trade_allocations",
        "simulation_state",
        "login_sessions",
        "login_credentials",
    ):
        op.drop_table(name)
    for name in ("generation_kwh", "load_kwh", "grid_import_kwh", "grid_export_kwh"):
        op.drop_column("telemetry_readings", name)
    # Enum values are intentionally retained: removing used values is destructive.
