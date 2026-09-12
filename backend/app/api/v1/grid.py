"""Grid digital-twin node endpoints.

Fulfills Phase-1 scope from docs/05_API_SPEC.md:
- GET /grid/nodes
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.grid import GridNodeListResponse, GridNodeResponse
from app.services import grid_service

router = APIRouter(prefix="/grid", tags=["grid"])


@router.get(
    "/nodes",
    response_model=GridNodeListResponse,
    summary="List digital-twin nodes",
)
def list_grid_nodes(
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=1000, description="Max nodes to return"),
    offset: int = Query(default=0, ge=0, description="Number of nodes to skip"),
) -> GridNodeListResponse:
    """Return a paginated list of distribution-grid nodes in the digital twin."""
    nodes, total = grid_service.list_grid_nodes(db, limit=limit, offset=offset)
    return GridNodeListResponse(
        items=[GridNodeResponse.model_validate(n) for n in nodes],
        total=total,
        limit=limit,
        offset=offset,
    )
