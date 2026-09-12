"""Grid domain Pydantic schemas.

Transport-layer DTOs only (docs/03_REPOSITORY_STRUCTURE.md).
Grid nodes are read-only from the REST API in Phase 1.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel


class NodeType(str, Enum):
    feeder = "feeder"
    bus = "bus"
    load = "load"
    generator = "generator"
    transformer = "transformer"


class GridNodeResponse(BaseModel):
    """Single grid node representation."""

    id: uuid.UUID
    external_ref: str | None
    node_type: NodeType
    nominal_voltage_kv: float | None
    parent_node_id: uuid.UUID | None
    feeder_id: str | None

    model_config = {"from_attributes": True}


class GridNodeListResponse(BaseModel):
    """GET /api/v1/grid/nodes paginated list."""

    items: list[GridNodeResponse]
    total: int
    limit: int
    offset: int
