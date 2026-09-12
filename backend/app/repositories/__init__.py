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
from app.repositories.telemetry import AggregatedReading, TelemetryRepository

__all__ = [
    "AggregatedReading",
    "BaseRepository",
    "ConsentRepository",
    "EnergyAssetRepository",
    "GridNodeRepository",
    "InverterDeviceRepository",
    "MeterRepository",
    "SiteRepository",
    "TelemetryRepository",
    "UserRepository",
    "UtilityAccountRepository",
    "VerificationRecordRepository",
]
