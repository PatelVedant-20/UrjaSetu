"""phase 5 grid capacity ratings

Adds the electrical capacity the digital twin was missing, so line and
transformer loading can be computed at all.

`grid_nodes` is extended rather than shadowed by a second edge table: this
topology is radial, so every node has at most one parent and an edge is
one-to-one with its lower node. A separate table would put topology in two
places. A meshed network or parallel circuits between the same pair of nodes
would break that correspondence, and is what would justify one later.

Revision ID: 0007_grid_capacity_ratings
Revises: 0006_grid_validation
Create Date: 2026-09-12 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_grid_capacity_ratings"
down_revision: str | None = "0006_grid_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, and left NULL for every existing row: the twin genuinely does
    # not know these ratings yet. A backfilled default would be an invented
    # denominator, and every loading percentage derived from it would be
    # fiction presented as measurement.
    op.add_column(
        "grid_nodes",
        sa.Column("rated_capacity_kw", sa.Numeric(precision=14, scale=4), nullable=True),
    )
    # `op.f` marks the name as final. Without it the metadata naming
    # convention prefixes it a second time, and the constraint lands as
    # `ck_grid_nodes_ck_grid_nodes_...` — which `alembic check` does not
    # notice, because autogenerate does not compare check constraints.
    op.create_check_constraint(
        op.f("ck_grid_nodes_rated_capacity_positive"),
        "grid_nodes",
        "rated_capacity_kw IS NULL OR rated_capacity_kw > 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_grid_nodes_rated_capacity_positive"), "grid_nodes", type_="check")
    op.drop_column("grid_nodes", "rated_capacity_kw")
