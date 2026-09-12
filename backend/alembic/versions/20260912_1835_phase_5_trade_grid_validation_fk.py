"""phase 5 trade grid validation fk

Gives `trades.grid_validation_id` a real target. The column has existed since
the market migration; until now nothing constrained it, so a trade could cite a
validation that had never happened.

The merged market migration is not touched — this is an ALTER on the table it
created.

Revision ID: 0008_trade_grid_validation_fk
Revises: 0007_grid_capacity_ratings
Create Date: 2026-09-12 18:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_trade_grid_validation_fk"
down_revision: str | None = "0007_grid_capacity_ratings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "fk_trades_grid_validation_id_grid_validation_runs"


def upgrade() -> None:
    op.create_index("ix_trades_grid_validation_id", "trades", ["grid_validation_id"], unique=False)
    # RESTRICT: the validation run is the evidence for whatever was decided
    # about this trade. Deleting it while the trade still cites it would leave
    # a decision with nothing behind it.
    op.create_foreign_key(
        CONSTRAINT,
        "trades",
        "grid_validation_runs",
        ["grid_validation_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "trades", type_="foreignkey")
    op.drop_index("ix_trades_grid_validation_id", table_name="trades")
