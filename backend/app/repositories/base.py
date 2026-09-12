"""Repository base.

Repositories are the only place that builds queries against persistence models
(docs/03_REPOSITORY_STRUCTURE.md). Services coordinate them; routers never see
them.

A repository never commits. The caller owns the transaction boundary, because
docs/04_DATA_MODEL.md defines those boundaries per business operation — order
creation, trade approval, settlement — not per row written.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Shared read/write operations for a single persistence model."""

    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: ModelT) -> ModelT:
        """Stage a new entity and flush so the database assigns defaults.

        Flushing (not committing) surfaces constraint violations here, where
        the offending operation is still on the stack, instead of at an
        unrelated commit later.
        """
        self.session.add(entity)
        self.session.flush()
        return entity

    def get(self, entity_id: UUID) -> ModelT | None:
        return self.session.get(self.model, entity_id)

    def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        stmt = select(self.model).limit(limit).offset(offset)
        return self.session.execute(stmt).scalars().all()

    def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        return self.session.execute(stmt).scalar_one()

    def delete(self, entity: ModelT) -> None:
        self.session.delete(entity)
        self.session.flush()

    def exists(self, entity_id: UUID) -> bool:
        return self.get(entity_id) is not None
