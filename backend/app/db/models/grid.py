"""Grid network digital-twin persistence models.

Represents the distribution-grid topology nodes used by the grid validation
engine and asset location (docs/04_DATA_MODEL.md section 4).

Grid nodes are pre-seeded via scripts/seed_dev.py; they are read-only from
the REST API in Phase 1. The API engineer exposes GET /grid/nodes only.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class GridNode(UUIDPrimaryKeyMixin, Base):
    """Electrical network node in the community digital twin.

    `node_type` values: feeder | bus | load | generator | transformer
    `nominal_voltage_kv` uses PostgreSQL NUMERIC for exact decimal representation.
    """

    __tablename__ = "grid_nodes"

    external_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # node_type: feeder | bus | load | generator | transformer
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    nominal_voltage_kv: Mapped[float | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("grid_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    feeder_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # self-referential: children nodes
    children: Mapped[list[GridNode]] = relationship(
        "GridNode", back_populates="parent", cascade="all"
    )
    parent: Mapped[GridNode | None] = relationship(
        "GridNode", back_populates="children", remote_side="GridNode.id"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GridNode id={self.id} type={self.node_type!r} ref={self.external_ref!r}>"
