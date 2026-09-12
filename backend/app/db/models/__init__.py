"""Persistence models.

Importing every model here is what populates `Base.metadata`, which is what
Alembic autogenerate compares against the live database. A model that is not
reachable from this module is invisible to migrations.
"""

from app.db.models.assets import (
    EnergyAsset,
    GridNode,
    InverterDevice,
    Meter,
    Site,
    VerificationRecord,
)
from app.db.models.forecasting import ForecastPoint, ForecastRun
from app.db.models.grid import GridSnapshot, GridValidationRun
from app.db.models.identity import Consent, User, UtilityAccount
from app.db.models.market import MarketSession, Order, Trade
from app.db.models.pricing import PriceComponents
from app.db.models.system_metadata import SystemMetadata
from app.db.models.telemetry import TelemetryReading

__all__ = [
    "Consent",
    "EnergyAsset",
    "ForecastPoint",
    "ForecastRun",
    "GridNode",
    "GridSnapshot",
    "GridValidationRun",
    "InverterDevice",
    "MarketSession",
    "Meter",
    "Order",
    "PriceComponents",
    "Site",
    "SystemMetadata",
    "Trade",
    "TelemetryReading",
    "User",
    "UtilityAccount",
    "VerificationRecord",
]
