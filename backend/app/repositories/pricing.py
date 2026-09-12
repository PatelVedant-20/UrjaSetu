"""Pricing persistence queries.

Query construction only — no formula, no coefficients, no decision rules
(docs/03_REPOSITORY_STRUCTURE.md). Never commits: the caller owns the
transaction boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select

from app.db.models.pricing import PriceComponents
from app.repositories.base import BaseRepository


class PriceComponentsRepository(BaseRepository[PriceComponents]):
    model = PriceComponents

    def latest_for_trade(self, trade_id: UUID) -> PriceComponents | None:
        """The breakdown that currently applies to a trade.

        The most recent calculation wins. Earlier ones are kept, so a price
        that was quoted and then superseded stays explainable.
        """
        stmt = (
            select(PriceComponents)
            .where(PriceComponents.trade_id == trade_id)
            .order_by(PriceComponents.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalars().first()

    def list_for_trade(self, trade_id: UUID) -> Sequence[PriceComponents]:
        """Every calculation made for a trade, oldest first."""
        stmt = (
            select(PriceComponents)
            .where(PriceComponents.trade_id == trade_id)
            .order_by(PriceComponents.created_at.asc())
        )
        return self.session.execute(stmt).scalars().all()
