"""Grid service for digital-twin node queries.

Coordinates read-only access to grid topology nodes in Phase 1
(docs/03_REPOSITORY_STRUCTURE.md, docs/05_API_SPEC.md).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.grid import GridNode


def list_grid_nodes(
    db: Session, limit: int = 100, offset: int = 0
) -> tuple[list[GridNode], int]:
    """Return paginated list of grid nodes and total count."""
    total = db.scalar(select(func.count()).select_from(GridNode)) or 0
    items = list(
        db.execute(
            select(GridNode)
            .order_by(GridNode.external_ref, GridNode.id)
            .limit(limit)
            .offset(offset)
        ).scalars().all()
    )
    return items, total
