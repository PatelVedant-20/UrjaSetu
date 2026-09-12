"""Audit persistence — `audit_events`.

Entity 21 of docs/04_DATA_MODEL.md, the `audit` module of
docs/01_FINAL_ARCHITECTURE.md.

Persistence only: no hashing, no serialization, no verification. Those live in
`app.domain.policies.audit_chain`, so the integrity scheme can change without a
schema change and so nothing that writes an event can compute a hash its own
way.

**Append-only.** No code path updates or deletes a row, the repository refuses
both, and a correction is a new event rather than an edit. The single
exception is `ledger_anchor_id`, which is written once when an event is
anchored externally — it is deliberately excluded from the hash, so recording
it cannot invalidate the chain.

**No `TimestampMixin`.** Every other table in the schema uses it; this one does
not, because its `updated_at` column would advertise a mutability an audit
ledger must not have. `recorded_at` replaces `created_at` and is written by the
service rather than by a server default, so the value that is hashed is the
value that is stored.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.models.identity import User
from app.db.types import pg_enum
from app.domain.enums import AuditEntityType, AuditEventType

# SHA-256, hex encoded.
_DIGEST = String(64)


class AuditEventRecord(Base, UUIDPrimaryKeyMixin):
    """One recorded business event (docs/04_DATA_MODEL.md entity 21).

    The row's primary key *is* the event id: the identity a business service
    generated is the identity that is hashed and stored, so an event cannot
    acquire a different one on its way into the database.

    Named `AuditEventRecord` rather than `AuditEvent` because
    `app.domain.interfaces.audit.AuditEvent` already holds that name for the
    domain contract. They are the same concept at two layers, not two competing
    contracts — the same relationship as `GridValidationResult` to
    `GridValidationRun`.
    """

    __tablename__ = "audit_events"

    event_type: Mapped[AuditEventType] = mapped_column(
        pg_enum(AuditEventType, "audit_event_type"), nullable=False
    )
    entity_type: Mapped[AuditEntityType] = mapped_column(
        pg_enum(AuditEntityType, "audit_entity_type"), nullable=False
    )
    # Polymorphic by design, and therefore not a foreign key: one audit log
    # spans orders, trades and market sessions, and a constraint per target
    # would mean either a column per entity type or a cascade that could delete
    # audit history. The entity type says how to interpret it.
    entity_id: Mapped[UUID] = mapped_column(nullable=False)

    # When the business event happened, and when the log recorded it. Both are
    # hashed; both are needed to audit an event recorded after the fact.
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # RESTRICT, never SET NULL: nulling this column on user deletion would
    # silently rewrite a hashed audit row and break the chain from that point
    # on. A user who appears in the audit log cannot be deleted, which is the
    # correct outcome for a financial audit trail.
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    payload_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    event_hash: Mapped[str] = mapped_column(_DIGEST, nullable=False)
    # NULL for exactly one row — the genesis of the chain.
    previous_hash: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)

    # Set once, if and when the event is anchored to an external ledger.
    # Excluded from the hash: anchoring is evidence *about* a recorded event,
    # and a hash that moved when evidence was published would invalidate the
    # chain the publication attests to.
    ledger_anchor_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    actor: Mapped[User | None] = relationship()

    __table_args__ = (
        # Two constraints that make forks impossible. Each hash may appear
        # once, and each predecessor may be claimed once — with NULLS NOT
        # DISTINCT so that "no predecessor" is also claimable only once, which
        # is what makes the genesis event unique. Together they mean the chain
        # is a line, not a tree, and the database says so rather than the
        # application hoping so.
        UniqueConstraint("event_hash", name="uq_audit_events_event_hash"),
        UniqueConstraint(
            "previous_hash",
            name="uq_audit_events_previous_hash",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint("length(event_hash) = 64", name="event_hash_is_sha256"),
        CheckConstraint(
            "previous_hash IS NULL OR length(previous_hash) = 64",
            name="previous_hash_is_sha256",
        ),
        CheckConstraint("event_hash <> previous_hash", name="event_does_not_follow_itself"),
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<AuditEventRecord id={self.id} type={self.event_type} "
            f"entity={self.entity_type}:{self.entity_id} hash={self.event_hash[:12]}>"
        )
