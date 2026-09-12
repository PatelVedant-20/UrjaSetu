"""`system_metadata` — the Phase 0 verification table.

Its only job is to prove the FastAPI -> SQLAlchemy -> PostgreSQL -> Alembic
chain end to end (docs/09_PHASE_0_SETUP.md Step 8). It is a real table with the
project's standard conventions, not a throwaway, so it doubles as the reference
example for Phase 1 models.

It is NOT a general-purpose key/value store for business data.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SystemMetadata(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "system_metadata"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SystemMetadata key={self.key!r}>"
