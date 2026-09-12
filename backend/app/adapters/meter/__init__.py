"""UrjaSetu Meter & Telemetry Adapters.

Provides source-agnostic adapters for transforming raw telemetry sources
(CSV, synthetic simulations, smart meters) into canonical normalized models.
"""

from __future__ import annotations

from app.adapters.meter.contracts import (
    AdapterError,
    AdapterParseError,
    AdapterValidationError,
    MeterReadingSource,
    NormalizedReading,
    NormalizedTelemetryBatch,
)
from app.adapters.meter.csv_adapter import TelemetryCSVAdapter
from app.adapters.meter.simulator_adapter import (
    MeterSimulatorAdapter,
    SyntheticTelemetryGenerator,
    make_deterministic_uuid,
)

__all__ = [
    "AdapterError",
    "AdapterParseError",
    "AdapterValidationError",
    "MeterSimulatorAdapter",
    "MeterReadingSource",
    "NormalizedReading",
    "NormalizedTelemetryBatch",
    "SyntheticTelemetryGenerator",
    "TelemetryCSVAdapter",
    "make_deterministic_uuid",
]
