"""Allow distinct partial executions while retaining duplicate-fill protection."""

import sqlalchemy as sa

from alembic import op

revision = "0015_trade_partial_fills"
down_revision = "0014_household_experience"
branch_labels = None
depends_on = None
CONSTRAINT = "uq_trades_buy_order_id_sell_order_id_delivery_start"


def upgrade() -> None:
    op.add_column(
        "trades", sa.Column("fill_sequence", sa.Integer(), nullable=False, server_default="1")
    )
    op.drop_constraint(CONSTRAINT, "trades", type_="unique")
    op.create_unique_constraint(
        CONSTRAINT, "trades", ["buy_order_id", "sell_order_id", "delivery_start", "fill_sequence"]
    )


def downgrade() -> None:
    # Fail safely if multiple executions now exist; do not delete trade history.
    op.drop_constraint(CONSTRAINT, "trades", type_="unique")
    op.create_unique_constraint(
        CONSTRAINT, "trades", ["buy_order_id", "sell_order_id", "delivery_start"]
    )
    op.drop_column("trades", "fill_sequence")
