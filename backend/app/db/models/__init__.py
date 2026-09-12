"""Persistence models.

Importing every model here is what populates `Base.metadata`, which is what
Alembic autogenerate compares against the live database. A model that is not
reachable from this module is invisible to migrations.

Import order matters for FK resolution:
  1. grid (no FK dependencies on other domain models)
  2. identity (FK to grid_nodes)
  3. assets (FK to users + grid_nodes)
"""

from app.db.models.assets import (
    EnergyAsset,
    InverterDevice,
    Meter,
    Site,
    VerificationRecord,
)
from app.db.models.grid import GridNode
from app.db.models.identity import Consent, User, UtilityAccount
from app.db.models.system_metadata import SystemMetadata

__all__ = [
    "SystemMetadata",
    # Phase-1 identity
    "User",
    "UtilityAccount",
    "Consent",
    # Phase-1 grid
    "GridNode",
    # Phase-1 assets
    "Site",
    "Meter",
    "EnergyAsset",
    "InverterDevice",
    "VerificationRecord",
]
