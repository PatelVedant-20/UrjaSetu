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
from app.repositories.forecasting import ForecastPointRepository, ForecastRunRepository
from app.repositories.grid import GridSnapshotRepository, GridValidationRunRepository
from app.repositories.identity import (
    ConsentRepository,
    UserRepository,
    UtilityAccountRepository,
)
from app.repositories.market import (
    MarketSessionRepository,
    OrderRepository,
    TradeRepository,
)
from app.repositories.pricing import PriceComponentsRepository
from app.repositories.telemetry import AggregatedReading, TelemetryRepository

__all__ = [
    "AggregatedReading",
    "BaseRepository",
    "ConsentRepository",
    "EnergyAssetRepository",
    "ForecastPointRepository",
    "ForecastRunRepository",
    "GridNodeRepository",
    "GridSnapshotRepository",
    "GridValidationRunRepository",
    "InverterDeviceRepository",
    "MarketSessionRepository",
    "MeterRepository",
    "OrderRepository",
    "PriceComponentsRepository",
    "SiteRepository",
    "TelemetryRepository",
    "TradeRepository",
    "UserRepository",
    "UtilityAccountRepository",
    "VerificationRecordRepository",
]
