"""Identity persistence models — `users`, `utility_accounts`, `consents`.

Maps the `identity` module of docs/01_FINAL_ARCHITECTURE.md onto entities 1, 2
and 9 of docs/04_DATA_MODEL.md.

Persistence only: no business rules, no API concerns, and no coupling to
forecasting, market, grid or ledger code.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.domain.enums import (
    ConsentScope,
    UserRole,
    UserStatus,
    VerificationLevel,
)

if TYPE_CHECKING:
    from app.db.models.assets import Site, VerificationRecord


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A platform identity (docs/04_DATA_MODEL.md entity 1)."""

    __tablename__ = "users"

    # Nullable and unique: the data model allows demo auth modes with no email.
    # PostgreSQL permits many NULLs under a unique constraint, so unverified
    # demo identities coexist while real addresses stay unique.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"),
        nullable=False,
        server_default=UserStatus.PENDING.value,
    )

    utility_accounts: Mapped[list[UtilityAccount]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    consents: Mapped[list[Consent]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    verification_records: Mapped[list[VerificationRecord]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # No delete-orphan: sites are structural, and the FK is RESTRICT so a user
    # with sites cannot be deleted out from under them.
    sites: Mapped[list[Site]] = relationship(back_populates="owner")

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name_not_blank"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} role={self.role} status={self.status}>"


class UtilityAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """DISCOM-facing identity metadata (docs/04_DATA_MODEL.md entity 2).

    One user may hold several utility accounts — the data model places the
    foreign key on this side and declares no uniqueness on `user_id`, so a
    prosumer with two service connections is representable.
    """

    __tablename__ = "utility_accounts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    discom_code: Mapped[str] = mapped_column(String(64), nullable=False)
    # Hash only. docs/04_DATA_MODEL.md: "Do not store raw production consumer
    # numbers in demo databases." The column name is part of that guarantee.
    consumer_number_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    verification_level: Mapped[VerificationLevel] = mapped_column(
        pg_enum(VerificationLevel, "verification_level"),
        nullable=False,
        server_default=VerificationLevel.NONE.value,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="utility_accounts")

    __table_args__ = (
        # One DISCOM consumer number is one account. Without this, the same
        # connection could be claimed twice and settled twice.
        UniqueConstraint(
            "discom_code",
            "consumer_number_hash",
            name="uq_utility_accounts_discom_code_consumer_number_hash",
        ),
        CheckConstraint(
            f"verification_level = '{VerificationLevel.NONE.value}' OR verified_at IS NOT NULL",
            name="verified_at_required_when_verified",
        ),
        Index("ix_utility_accounts_user_id", "user_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<UtilityAccount id={self.id} discom={self.discom_code}>"


class Consent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Consent trail for device/meter data (docs/04_DATA_MODEL.md entity 9).

    Rows are a trail, not a toggle: revoking sets `revoked_at` rather than
    deleting, so the grant remains explainable afterwards
    (docs/00_PROJECT_BIBLE.md: traceability).
    """

    __tablename__ = "consents"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[ConsentScope] = mapped_column(
        pg_enum(ConsentScope, "consent_scope"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="consents")

    @property
    def is_active(self) -> bool:
        """True while the grant stands. Pure derivation, no I/O."""
        return self.revoked_at is None

    __table_args__ = (
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= granted_at",
            name="revoked_after_granted",
        ),
        Index("ix_consents_user_id_scope", "user_id", "scope"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Consent id={self.id} scope={self.scope} active={self.is_active}>"
