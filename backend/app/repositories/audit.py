"""Audit persistence queries.

Query construction only — no hashing, no serialization, no verification
(docs/03_REPOSITORY_STRUCTURE.md). Never commits: the caller owns the
transaction boundary.

This repository is deliberately narrower than the others: it can append and it
can read, and it refuses to delete. An audit log that supports deletion is not
an audit log.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn
from uuid import UUID

from sqlalchemy import func, select

from app.db.models.audit import AuditEventRecord
from app.domain.enums import AuditEntityType, AuditEventType
from app.repositories.base import BaseRepository


class AuditAppendOnlyError(RuntimeError):
    """Raised on any attempt to remove a recorded audit event."""


class AuditEventRepository(BaseRepository[AuditEventRecord]):
    model = AuditEventRecord

    def delete(self, entity: AuditEventRecord) -> NoReturn:
        """Refused, always.

        `BaseRepository` offers deletion to every other model; overriding it
        here means the append-only rule is enforced by the type system rather
        than by everyone remembering it. A mistaken correction appends a new
        event instead.
        """
        raise AuditAppendOnlyError(
            "Audit events are append-only. Record a corrective event instead of " "deleting one."
        )

    def latest(self) -> AuditEventRecord | None:
        """The current head of the chain.

        Ordered by `recorded_at` with the event id as a tiebreaker, so two
        events recorded in the same microsecond still have one deterministic
        order — which matters, because the head decides what the next event
        links to.
        """
        stmt = (
            select(AuditEventRecord)
            .order_by(AuditEventRecord.recorded_at.desc(), AuditEventRecord.id.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def list_chain(self, *, limit: int | None = None) -> Sequence[AuditEventRecord]:
        """The whole chain in recorded order, oldest first.

        This is the order verification walks. It is not re-sorted downstream:
        the order is part of what is being checked.
        """
        stmt = select(AuditEventRecord).order_by(
            AuditEventRecord.recorded_at.asc(), AuditEventRecord.id.asc()
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.session.execute(stmt).scalars().all()

    def list_for_entity(
        self, entity_type: AuditEntityType, entity_id: UUID
    ) -> Sequence[AuditEventRecord]:
        """One entity's timeline, oldest first.

        Backs `GET /audit/entities/{entity_type}/{entity_id}`. Asking for a
        trade returns its whole economic lifecycle — proposal, grid validation,
        price, reconciliation, settlement — because those events are all
        recorded against the trade.
        """
        stmt = (
            select(AuditEventRecord)
            .where(
                AuditEventRecord.entity_type == entity_type,
                AuditEventRecord.entity_id == entity_id,
            )
            .order_by(AuditEventRecord.recorded_at.asc(), AuditEventRecord.id.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def get_by_hash(self, event_hash: str) -> AuditEventRecord | None:
        stmt = select(AuditEventRecord).where(AuditEventRecord.event_hash == event_hash)
        return self.session.execute(stmt).scalars().first()

    def count_by_type(self) -> dict[AuditEventType, int]:
        stmt = select(AuditEventRecord.event_type, func.count(AuditEventRecord.id)).group_by(
            AuditEventRecord.event_type
        )
        return dict(self.session.execute(stmt).all())  # type: ignore[arg-type]

    def unanchored(self, *, limit: int = 100) -> Sequence[AuditEventRecord]:
        """Recorded events that have not been published to a ledger.

        The queue a future publisher drains. Empty of meaning until one is
        configured, and harmless when none ever is.
        """
        stmt = (
            select(AuditEventRecord)
            .where(AuditEventRecord.ledger_anchor_id.is_(None))
            .order_by(AuditEventRecord.recorded_at.asc())
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()
