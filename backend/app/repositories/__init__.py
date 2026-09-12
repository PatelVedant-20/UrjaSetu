"""Repositories — the query/persistence layer.

Services coordinate these; routers never import them
(docs/03_REPOSITORY_STRUCTURE.md ownership rules).
"""

from app.repositories.assets import (
    EnergyAssetRepository,
    GridNodeRepository,
    InverterDeviceRepository,
    MeterRepository,
    SiteRepository,
    VerificationRecordRepository,
)
from app.repositories.base import BaseRepository
from app.repositories.identity import (
    ConsentRepository,
    UserRepository,
    UtilityAccountRepository,
)

__all__ = [
    "BaseRepository",
    "ConsentRepository",
    "EnergyAssetRepository",
    "GridNodeRepository",
    "InverterDeviceRepository",
    "MeterRepository",
    "SiteRepository",
    "UserRepository",
    "UtilityAccountRepository",
    "VerificationRecordRepository",
]
