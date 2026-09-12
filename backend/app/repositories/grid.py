"""Grid persistence queries.

Query construction only — no power flow, no limits, no decision rules
(docs/03_REPOSITORY_STRUCTURE.md). Never commits: the caller owns the
transaction boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.db.models.grid import GridSnapshot, GridValidationRun
from app.domain.enums import GridValidationDecision
from app.repositories.base import BaseRepository


class GridSnapshotRepository(BaseRepository[GridSnapshot]):
    model = GridSnapshot

    def latest_for_feeder(self, feeder_id: str) -> GridSnapshot | None:
        """Most recently captured state of a feeder.

        By `captured_at` — when the network was observed — not by when the row
        was written, so a late-arriving snapshot of an earlier moment does not
        masquerade as current.
        """
        stmt = (
            select(GridSnapshot)
            .where(GridSnapshot.feeder_id == feeder_id)
            .order_by(GridSnapshot.captured_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def list_for_feeder(
        self, feeder_id: str, *, start: datetime, end: datetime
    ) -> Sequence[GridSnapshot]:
        stmt = (
            select(GridSnapshot)
            .where(
                GridSnapshot.feeder_id == feeder_id,
                GridSnapshot.captured_at >= start,
                GridSnapshot.captured_at <= end,
            )
            .order_by(GridSnapshot.captured_at.asc())
        )
        return self.session.execute(stmt).scalars().all()


class GridValidationRunRepository(BaseRepository[GridValidationRun]):
    model = GridValidationRun

    def list_for_trade(self, trade_id: UUID) -> Sequence[GridValidationRun]:
        """Every validation attempted for a trade, oldest first.

        A trade may be re-validated as the network changes; the history is kept
        rather than overwritten, so a decision stays explainable afterwards.
        """
        stmt = (
            select(GridValidationRun)
            .where(GridValidationRun.trade_id == trade_id)
            .order_by(GridValidationRun.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def latest_for_trade(self, trade_id: UUID) -> GridValidationRun | None:
        stmt = (
            select(GridValidationRun)
            .where(GridValidationRun.trade_id == trade_id)
            .order_by(GridValidationRun.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def find_by_input_hash(self, input_hash: str) -> GridValidationRun | None:
        """A previous run of an identical scenario, if one exists."""
        stmt = (
            select(GridValidationRun)
            .where(GridValidationRun.input_hash == input_hash)
            .order_by(GridValidationRun.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def count_by_decision(self) -> dict[GridValidationDecision, int]:
        from sqlalchemy import func

        stmt = select(GridValidationRun.decision, func.count(GridValidationRun.id)).group_by(
            GridValidationRun.decision
        )
        return dict(self.session.execute(stmt).all())  # type: ignore[arg-type]
