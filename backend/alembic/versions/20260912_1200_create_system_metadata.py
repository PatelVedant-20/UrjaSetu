"""create system_metadata

The Phase 0 verification table. Proves that
FastAPI -> SQLAlchemy -> PostgreSQL -> Alembic works from an empty database
(docs/09_PHASE_0_SETUP.md Step 8).

Revision ID: 0001_system_metadata
Revises:
Create Date: 2026-09-12 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_system_metadata"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_metadata",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_metadata")),
    )
    op.create_index(op.f("ix_system_metadata_key"), "system_metadata", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_system_metadata_key"), table_name="system_metadata")
    op.drop_table("system_metadata")
