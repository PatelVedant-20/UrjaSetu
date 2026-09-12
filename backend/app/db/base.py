"""SQLAlchemy declarative base and shared column conventions.

Everything persisted by UrjaSetu inherits from `Base`, so every table gets the
same primary-key type, timestamp semantics and constraint naming.

Phase 0 defines the conventions only. The real UrjaSetu schema
(docs/04_DATA_MODEL.md) is built in Phase 1 and later.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint/index names. Without this, PostgreSQL invents names
# and Alembic autogenerate produces unstable, unreviewable diffs — and dropping
# a constraint in a later migration becomes guesswork.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base carrying UrjaSetu's shared metadata."""

    metadata = metadata_obj


class UUIDPrimaryKeyMixin:
    """UUID primary keys everywhere (docs/00_PROJECT_BIBLE.md section 6).

    Generated application-side so a caller can know an entity's ID before the
    transaction commits — which matters for the audit trail and for correlating
    events across services.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """`created_at` / `updated_at` as timezone-aware UTC.

    Defaults are server-side so rows written outside the ORM (migrations, bulk
    loads, psql) still get correct timestamps.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
