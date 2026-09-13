"""Personal household settings and idempotent direct trades."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0014_household_experience"
down_revision = "0013_order_cancellation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "simulation_state",
        sa.Column("live_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "household_profiles",
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("settings", JSONB(), nullable=False),
        sa.Column("avatar", sa.Text()),
        sa.Column("photo", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "marketplace_actions",
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("request_id", sa.UUID(), primary_key=True),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("trade_id", sa.UUID(), sa.ForeignKey("trades.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("marketplace_actions")
    op.drop_table("household_profiles")
    op.drop_column("simulation_state", "live_mode")
