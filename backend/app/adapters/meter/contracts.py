
"""UrjaSetu Telemetry Adapter Contracts.

This module defines the source-agnostic normalized telemetry contracts and
exceptions produced by input adapters (CSV parsers, synthetic simulators,
and future hardware/AMI/SunSpec adapters) before handing off to the telemetry
service (docs/00_PROJECT_BIBLE.md, docs/04_DATA_MODEL.md).

DOWNSTREAM CONTRACT:
Downstream domain services receive ONLY these normalized models. They are
completely decoupled from CSV columns, file structures, or vendor protocols.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdapterError(Exception):
    """Base exception for all telemetry adapter errors."""


class AdapterParseError(AdapterError):
    """Raised when raw telemetry input (e.g. CSV, JSON, payload) is syntactically malformed."""

    def __init__(
        self, message: str, line_number: int | None = None, raw_data: str | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line_number = line_number
        self.raw_data = raw_data


class AdapterValidationError(AdapterError):
    """Raised when adapter-level validation fails (e.g. missing columns, invalid numeric values)."""

    def __init__(
        self,
        message: str,
        line_number: int | None = None,
        field_name: str | None = None,
        invalid_value: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line_number = line_number
        self.field_name = field_name
        self.invalid_value = invalid_value


class NormalizedTelemetryReading(BaseModel):
    """Normalized energy telemetry reading.

    Matches the canonical fields specified in docs/04_DATA_MODEL.md section 10
    and docs/00_PROJECT_BIBLE.md section 6:
    - Power in kW (generation_kw, load_kw, grid_import_kw, grid_export_kw)
    - Energy in kWh (energy_kwh)
    - Time in UTC timezone-aware datetimes with explicit interval boundaries.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    meter_id: UUID = Field(..., description="UUID of the reporting smart/net meter")
    site_id: UUID | None = Field(
        default=None,
        description="Optional site identifier if known at adapter ingestion boundary",
    )
    energy_asset_id: UUID | None = Field(
        default=None,
        description="Optional asset UUID (e.g. PV system) associated with this reading",
    )
    timestamp: datetime = Field(
        ...,
        description="Reading timestamp in UTC",
    )
    interval_start: datetime = Field(
        ...,
        description="Start of the measurement window (UTC)",
    )
    interval_end: datetime = Field(
        ...,
        description="End of the measurement window (UTC)",
    )
    generation_kw: Decimal = Field(
        default=Decimal("0.0"),
        description="Active power generation in kW (non-negative)",
    )
    load_kw: Decimal = Field(
        default=Decimal("0.0"),
        description="Active power demand/load in kW (non-negative)",
    )
    grid_import_kw: Decimal = Field(
        default=Decimal("0.0"),
        description="Active power imported from the grid in kW (non-negative)",
    )
    grid_export_kw: Decimal = Field(
        default=Decimal("0.0"),
        description="Active power exported to the grid in kW (non-negative)",
    )
    energy_kwh: Decimal | None = Field(
        default=None,
        description="Cumulative or interval energy in kWh if provided by meter",
    )
    voltage_pu: Decimal | None = Field(
        default=None,
        description="Optional per-unit voltage measurement (e.g. 1.02 pu)",
    )
    battery_soc: Decimal | None = Field(
        default=None,
        description="Optional battery State of Charge in percentage (0.0 to 100.0)",
    )
    source: str = Field(
        default="simulator",
        description="Source identifier (e.g. 'csv_simulator', 'synthetic_generator', 'sunspec')",
    )
    raw_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional diagnostic/audit metadata from original raw ingestion",
    )

    @field_validator("timestamp", "interval_start", "interval_end", mode="after")
    @classmethod
    def _enforce_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            # Assume UTC if naive, attach UTC timezone
            return v.replace(tzinfo=UTC)
        return v.astimezone(UTC)

    @field_validator("generation_kw", "load_kw", "grid_import_kw", "grid_export_kw", mode="after")
    @classmethod
    def _enforce_non_negative_power(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.0"):
            raise ValueError(f"Power measurement cannot be negative: {v}")
        return v

    @field_validator("battery_soc", mode="after")
    @classmethod
    def _validate_battery_soc(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and not (Decimal("0.0") <= v <= Decimal("100.0")):
            raise ValueError(f"Battery SoC must be between 0.0 and 100.0, got: {v}")
        return v


class NormalizedTelemetryBatch(BaseModel):
    """Container for a batch of normalized readings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_name: str = Field(..., description="Name or path of the input source")
    readings: list[NormalizedTelemetryReading] = Field(
        default_factory=list,
        description="List of successfully normalized telemetry records",
    )
    total_records: int = Field(
        default=0,
        description="Total number of records processed",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="List of error messages encountered for failed rows (if resilient mode)",
    )


@runtime_checkable
class TelemetryIngestionProtocol(Protocol):
    """Protocol for downstream telemetry service ingestion.

    Decouples the adapter from concrete service implementations.
    Yagnik's TelemetryService can implement this interface.
    """

    def ingest_normalized_readings(
        self,
        readings: list[NormalizedTelemetryReading],
    ) -> Any:
        """Ingest a batch of normalized readings into the system."""
        ...
