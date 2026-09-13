"""Audit cancelled reservations explicitly."""

from alembic import op

revision = "0013_order_cancellation"
down_revision = "0012_connected_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_event_type ADD VALUE IF NOT EXISTS 'order_cancelled'")


def downgrade() -> None:
    # PostgreSQL enum values are retained to preserve historical evidence.
    pass
