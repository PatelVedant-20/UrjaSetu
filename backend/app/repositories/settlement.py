"""Settlement persistence queries.

Query construction only — no tolerance, no accounting, no decision rules
(docs/03_REPOSITORY_STRUCTURE.md). Never commits: the caller owns the
transaction boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from app.db.models.settlement import MeterReconciliation, Settlement
from app.domain.enums import SettlementStatus
from app.repositories.base import BaseRepository


class MeterReconciliationRepository(BaseRepository[MeterReconciliation]):
    model = MeterReconciliation

    def latest_for_trade(self, trade_id: UUID) -> MeterReconciliation | None:
        """The comparison that currently stands for a trade."""
        stmt = (
            select(MeterReconciliation)
            .where(MeterReconciliation.trade_id == trade_id)
            .order_by(MeterReconciliation.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def list_for_trade(self, trade_id: UUID) -> Sequence[MeterReconciliation]:
        """Every comparison made for a trade, oldest first.

        A trade may be reconciled again as late telemetry arrives; the earlier
        attempts are kept so the sequence stays explainable.
        """
        stmt = (
            select(MeterReconciliation)
            .where(MeterReconciliation.trade_id == trade_id)
            .order_by(MeterReconciliation.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()


class SettlementRepository(BaseRepository[Settlement]):
    model = Settlement

    def active_for_trade(self, trade_id: UUID) -> Settlement | None:
        """The settlement that currently stands, ignoring superseded ones."""
        stmt = (
            select(Settlement)
            .where(
                Settlement.trade_id == trade_id,
                Settlement.status != SettlementStatus.SUPERSEDED,
            )
            .order_by(Settlement.settled_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def list_for_trade(self, trade_id: UUID) -> Sequence[Settlement]:
        """Every settlement written for a trade, oldest first — including
        superseded ones, which are the audit trail of a correction."""
        stmt = (
            select(Settlement)
            .where(Settlement.trade_id == trade_id)
            .order_by(Settlement.settled_at.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_for_user(self, user_id: UUID) -> Sequence[Settlement]:
        """A user's settlement history, newest first, as either party.

        Backs `GET /users/{user_id}/settlements`.
        """
        stmt = (
            select(Settlement)
            .where((Settlement.buyer_user_id == user_id) | (Settlement.seller_user_id == user_id))
            .order_by(Settlement.settled_at.desc())
        )
        return self.session.execute(stmt).scalars().all()
