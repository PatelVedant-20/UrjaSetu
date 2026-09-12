"""CSV Telemetry Ingestion Adapter for UrjaSetu.

Converts raw CSV inputs (files, text streams, or strings) into canonical
`NormalizedReading` objects conforming to docs/04_DATA_MODEL.md.

SOURCE AGNOSTIC:
Downstream consumers (e.g. Yagnik's TelemetryService) only interact with
`NormalizedReading` and have zero coupling to CSV headers or formats.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TextIO
from uuid import UUID

from app.adapters.meter.contracts import (
    AdapterParseError,
    AdapterValidationError,
    NormalizedReading,
    NormalizedTelemetryBatch,
)
from app.domain.enums import TelemetrySource

# Canonical column synonym mappings
_COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "timestamp": (
        "timestamp",
        "datetime",
        "date_time",
        "time",
        "ts",
        "reading_time",
        "interval_start",
    ),
    "interval_start": ("interval_start", "start_time", "start"),
    "interval_end": ("interval_end", "end_time", "end"),
    "meter_id": ("meter_id", "meter_uuid", "meter", "meter_id_ref"),
    "site_id": ("site_id", "site_uuid", "site"),
    "energy_asset_id": ("energy_asset_id", "asset_id", "asset_uuid", "pv_id", "solar_asset_id"),
    "generation_kw": (
        "generation_kw",
        "gen_kw",
        "solar_kw",
        "pv_kw",
        "generation",
        "solar_generation_kw",
    ),
    "load_kw": ("load_kw", "demand_kw", "consumption_kw", "load", "power_demand_kw"),
    "grid_import_kw": ("grid_import_kw", "import_kw", "grid_import", "imported_kw"),
    "grid_export_kw": ("grid_export_kw", "export_kw", "grid_export", "exported_kw"),
    "energy_kwh": ("energy_kwh", "kwh", "energy", "active_energy_kwh"),
    "voltage_pu": ("voltage_pu", "v_pu", "voltage"),
    "battery_soc": ("battery_soc", "soc", "battery_percentage", "state_of_charge"),
}


def _normalize_header(raw_header: str) -> str:
    """Normalize header string to lowercase stripped alphanumeric with underscores."""
    return raw_header.strip().lower().replace("-", "_").replace(" ", "_")


def _find_column(field_key: str, available_headers: dict[str, str]) -> str | None:
    """Find the actual CSV column name corresponding to a canonical field."""
    synonyms = _COLUMN_SYNONYMS.get(field_key, (field_key,))
    for syn in synonyms:
        if syn in available_headers:
            return available_headers[syn]
    return None


def _parse_timestamp(raw_value: str, line_num: int) -> datetime:
    """Parse various timestamp string representations into timezone-aware UTC datetime."""
    val = raw_value.strip()
    if not val:
        raise AdapterValidationError(
            message="Timestamp value cannot be empty",
            line_number=line_num,
            field_name="timestamp",
            invalid_value=raw_value,
        )

    # 1. Try ISO format directly
    # Handles 2026-09-12T12:00:00Z, 2026-09-12T12:00:00+00:00, 2026-09-12 12:00:00
    try:
        # Replace 'Z' with '+00:00' for standard fromisoformat if needed
        clean_iso = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_iso)
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except ValueError:
        pass

    # 2. Try common datetime patterns
    common_formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in common_formats:
        try:
            dt = datetime.strptime(val, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue

    # 3. Try epoch timestamp (seconds or milliseconds)
    try:
        epoch_num = float(val)
        if not math.isfinite(epoch_num):
            raise ValueError()
        if epoch_num > 1e11:  # Milliseconds
            return datetime.fromtimestamp(epoch_num / 1000.0, tz=UTC)
        return datetime.fromtimestamp(epoch_num, tz=UTC)
    except (ValueError, OverflowError):
        pass

    raise AdapterValidationError(
        message=f"Invalid timestamp format: '{raw_value}'",
        line_number=line_num,
        field_name="timestamp",
        invalid_value=raw_value,
    )


def _parse_decimal(
    raw_value: Any,
    field_name: str,
    line_num: int,
    default: Decimal | None = None,
    allow_none: bool = False,
    non_negative: bool = True,
) -> Decimal | None:
    """Parse a numeric string into Decimal with strict validation."""
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        if default is not None:
            return default
        if allow_none:
            return None
        raise AdapterValidationError(
            message=f"Field '{field_name}' cannot be empty",
            line_number=line_num,
            field_name=field_name,
            invalid_value=raw_value,
        )

    val_str = str(raw_value).strip()
    try:
        val = Decimal(val_str)
        if not val.is_finite():
            raise InvalidOperation()
    except (InvalidOperation, TypeError) as err:
        raise AdapterValidationError(
            message=f"Field '{field_name}' must be a valid number, got: '{raw_value}'",
            line_number=line_num,
            field_name=field_name,
            invalid_value=raw_value,
        ) from err

    if non_negative and val < Decimal("0.0"):
        raise AdapterValidationError(
            message=f"Field '{field_name}' cannot be negative, got: {val}",
            line_number=line_num,
            field_name=field_name,
            invalid_value=val,
        )

    return val


def _parse_uuid(
    raw_value: Any,
    field_name: str,
    line_num: int,
    default: UUID | None = None,
    allow_none: bool = False,
) -> UUID | None:
    """Parse a UUID string with validation."""
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        if default is not None:
            return default
        if allow_none:
            return None
        raise AdapterValidationError(
            message=f"Missing required UUID for field '{field_name}'",
            line_number=line_num,
            field_name=field_name,
            invalid_value=raw_value,
        )

    val_str = str(raw_value).strip()
    try:
        return UUID(val_str)
    except (ValueError, AttributeError) as err:
        raise AdapterValidationError(
            message=f"Invalid UUID for field '{field_name}': '{raw_value}'",
            line_number=line_num,
            field_name=field_name,
            invalid_value=raw_value,
        ) from err


class TelemetryCSVAdapter:
    """Adapter for parsing and normalizing raw telemetry CSV streams or files."""

    def __init__(
        self,
        default_meter_id: UUID | None = None,
        default_site_id: UUID | None = None,
        default_energy_asset_id: UUID | None = None,
        default_interval_minutes: int = 15,
        source_name: str = "csv_simulator",
        strict: bool = True,
    ) -> None:
        """Initialize the CSV adapter.

        Args:
            default_meter_id: Fallback meter UUID if not in CSV columns.
            default_site_id: Fallback site UUID if not in CSV columns.
            default_energy_asset_id: Fallback asset UUID if not in CSV columns.
            default_interval_minutes: Default window duration if interval_end is missing.
            source_name: Name/identifier of the data source.
            strict: If True, raise on first error. If False, skip invalid rows and record errors.
        """
        self.default_meter_id = default_meter_id
        self.default_site_id = default_site_id
        self.default_energy_asset_id = default_energy_asset_id
        self.default_interval_minutes = default_interval_minutes
        self.source_name = source_name
        self.strict = strict
        # Populated by parse_*; replayed by read().
        self._last_batch = NormalizedTelemetryBatch(source_name=source_name)

    def read(self, *, since: datetime | None = None) -> list[NormalizedReading]:
        """Yield normalized readings, oldest first.

        Satisfies `app.domain.interfaces.telemetry.MeterReadingSource`, so the
        telemetry service can consume this adapter without knowing it parses
        CSV. Requires a source to have been configured via `parse_*`; this
        method replays what the most recent parse produced.
        """
        readings = sorted(self._last_batch.readings, key=lambda r: r.interval_start)
        if since is not None:
            readings = [r for r in readings if r.interval_start >= since]
        return readings

    def parse_file(self, file_path: str | Path) -> NormalizedTelemetryBatch:
        """Parse a CSV file from the filesystem."""
        path = Path(file_path)
        if not path.is_file():
            raise AdapterParseError(f"File not found: {file_path}")

        try:
            with open(path, encoding="utf-8-sig") as f:
                return self.parse_stream(f, source_name=str(path.name))
        except UnicodeDecodeError as e:
            raise AdapterParseError(f"File encoding error in '{file_path}': {e}") from e

    def parse_string(
        self, csv_content: str, source_name: str | None = None
    ) -> NormalizedTelemetryBatch:
        """Parse a CSV content string."""
        if not csv_content or not csv_content.strip():
            raise AdapterValidationError("CSV input is empty")
        stream = io.StringIO(csv_content)
        return self.parse_stream(stream, source_name=source_name or self.source_name)

    def parse_stream(
        self,
        stream: TextIO,
        source_name: str | None = None,
    ) -> NormalizedTelemetryBatch:
        """Parse a text stream containing CSV data."""
        actual_source = source_name or self.source_name
        readings: list[NormalizedReading] = []
        errors: list[str] = []
        total_rows = 0

        try:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise AdapterValidationError("CSV input is empty or has no header row")

            # Clean and map headers
            raw_fieldnames = [fn for fn in reader.fieldnames if fn is not None]
            if not raw_fieldnames:
                raise AdapterValidationError("CSV contains no valid headers")

            header_map: dict[str, str] = {_normalize_header(fn): fn for fn in raw_fieldnames}

            # Verify required timestamp column exists
            ts_col = _find_column("timestamp", header_map)
            if not ts_col:
                raise AdapterValidationError(
                    f"Missing required timestamp column. Available headers: {raw_fieldnames}"
                )

            # Find mapped columns
            int_start_col = _find_column("interval_start", header_map)
            int_end_col = _find_column("interval_end", header_map)
            meter_col = _find_column("meter_id", header_map)
            site_col = _find_column("site_id", header_map)
            asset_col = _find_column("energy_asset_id", header_map)
            gen_col = _find_column("generation_kw", header_map)
            load_col = _find_column("load_kw", header_map)
            import_col = _find_column("grid_import_kw", header_map)
            export_col = _find_column("grid_export_kw", header_map)
            energy_col = _find_column("energy_kwh", header_map)
            volt_col = _find_column("voltage_pu", header_map)
            soc_col = _find_column("battery_soc", header_map)

            # Process rows (1-indexed CSV data rows starting after header, so line 2)
            for line_idx, row in enumerate(reader, start=2):
                # Ignore empty trailing lines
                if not any(row.values()):
                    continue

                total_rows += 1
                try:
                    reading = self._parse_row(
                        row=row,
                        line_num=line_idx,
                        ts_col=ts_col,
                        int_start_col=int_start_col,
                        int_end_col=int_end_col,
                        meter_col=meter_col,
                        site_col=site_col,
                        asset_col=asset_col,
                        gen_col=gen_col,
                        load_col=load_col,
                        import_col=import_col,
                        export_col=export_col,
                        energy_col=energy_col,
                        volt_col=volt_col,
                        soc_col=soc_col,
                    )
                    readings.append(reading)
                except (AdapterValidationError, AdapterParseError) as e:
                    if self.strict:
                        raise
                    errors.append(
                        f"Line {line_idx}: {e.message if hasattr(e, 'message') else str(e)}"
                    )
                except Exception as e:
                    if self.strict:
                        raise AdapterValidationError(
                            message=f"Unexpected parsing error: {e}",
                            line_number=line_idx,
                        ) from e
                    errors.append(f"Line {line_idx}: Unexpected error - {e}")

        except csv.Error as e:
            raise AdapterParseError(f"Malformed CSV syntax: {e}") from e

        if total_rows == 0 and not readings:
            raise AdapterValidationError("CSV input contains no data rows")

        self._last_batch = NormalizedTelemetryBatch(
            source_name=actual_source,
            readings=readings,
            total_records=total_rows,
            errors=errors,
        )
        return self._last_batch

    def _parse_row(
        self,
        row: dict[str, Any],
        line_num: int,
        ts_col: str,
        int_start_col: str | None,
        int_end_col: str | None,
        meter_col: str | None,
        site_col: str | None,
        asset_col: str | None,
        gen_col: str | None,
        load_col: str | None,
        import_col: str | None,
        export_col: str | None,
        energy_col: str | None,
        volt_col: str | None,
        soc_col: str | None,
    ) -> NormalizedReading:
        """Parse an individual CSV row into a NormalizedReading."""
        # 1. Parse timestamp
        raw_ts = row.get(ts_col)
        if not raw_ts:
            raise AdapterValidationError(
                message=f"Missing timestamp in column '{ts_col}'",
                line_number=line_num,
                field_name="timestamp",
            )
        ts = _parse_timestamp(raw_ts, line_num)

        # 2. Derive interval_start and interval_end
        if int_start_col and row.get(int_start_col):
            interval_start = _parse_timestamp(row[int_start_col], line_num)
        else:
            interval_start = ts

        if int_end_col and row.get(int_end_col):
            interval_end = _parse_timestamp(row[int_end_col], line_num)
        else:
            interval_end = interval_start + timedelta(minutes=self.default_interval_minutes)

        if interval_end <= interval_start:
            raise AdapterValidationError(
                message=(
                    f"interval_end ({interval_end.isoformat()}) must be strictly after "
                    f"interval_start ({interval_start.isoformat()})"
                ),
                line_number=line_num,
                field_name="interval_end",
            )

        # 3. Parse IDs
        raw_meter = row.get(meter_col) if meter_col else None
        meter_id = _parse_uuid(
            raw_meter,
            field_name="meter_id",
            line_num=line_num,
            default=self.default_meter_id,
        )
        assert meter_id is not None  # enforced by _parse_uuid

        # A `site_id` column is tolerated in the input but not carried into the
        # reading: docs/04_DATA_MODEL.md entity 10 has no site_id, because a
        # reading's site is reached through its meter.

        raw_asset = row.get(asset_col) if asset_col else None
        asset_id = _parse_uuid(
            raw_asset,
            field_name="energy_asset_id",
            line_num=line_num,
            default=self.default_energy_asset_id,
            allow_none=True,
        )

        # 4. Parse power measurements (kW)
        raw_gen = row.get(gen_col) if gen_col else None
        gen_kw = _parse_decimal(
            raw_gen,
            field_name="generation_kw",
            line_num=line_num,
            default=Decimal("0.0"),
            non_negative=True,
        ) or Decimal("0.0")

        raw_load = row.get(load_col) if load_col else None
        load_kw = _parse_decimal(
            raw_load,
            field_name="load_kw",
            line_num=line_num,
            default=Decimal("0.0"),
            non_negative=True,
        ) or Decimal("0.0")

        raw_import = row.get(import_col) if import_col else None
        raw_export = row.get(export_col) if export_col else None

        # Derive grid import/export if not explicitly provided
        if raw_import is not None or raw_export is not None:
            grid_import_kw = _parse_decimal(
                raw_import,
                field_name="grid_import_kw",
                line_num=line_num,
                default=Decimal("0.0"),
                non_negative=True,
            ) or Decimal("0.0")
            grid_export_kw = _parse_decimal(
                raw_export,
                field_name="grid_export_kw",
                line_num=line_num,
                default=Decimal("0.0"),
                non_negative=True,
            ) or Decimal("0.0")
        else:
            # Physical balance derivation: net = load - generation
            net_demand = load_kw - gen_kw
            if net_demand >= Decimal("0.0"):
                grid_import_kw = net_demand
                grid_export_kw = Decimal("0.0")
            else:
                grid_import_kw = Decimal("0.0")
                grid_export_kw = abs(net_demand)

        # 5. Optional measurements
        raw_energy = row.get(energy_col) if energy_col else None
        energy_kwh = _parse_decimal(
            raw_energy,
            field_name="energy_kwh",
            line_num=line_num,
            allow_none=True,
            non_negative=True,
        )

        # `voltage_pu` is likewise tolerated but not stored. Voltage is a grid
        # quantity (docs/04_DATA_MODEL.md entity 16, `grid_snapshots`), not a
        # telemetry reading channel, and belongs to the Phase 6 digital twin.

        raw_soc = row.get(soc_col) if soc_col else None
        battery_soc = _parse_decimal(
            raw_soc,
            field_name="battery_soc",
            line_num=line_num,
            allow_none=True,
            non_negative=True,
        )
        if battery_soc is not None and not (Decimal("0.0") <= battery_soc <= Decimal("100.0")):
            raise AdapterValidationError(
                message=f"battery_soc must be between 0.0 and 100.0, got: {battery_soc}",
                line_number=line_num,
                field_name="battery_soc",
                invalid_value=battery_soc,
            )

        return NormalizedReading(
            meter_id=meter_id,
            energy_asset_id=asset_id,
            timestamp=ts,
            interval_start=interval_start,
            interval_end=interval_end,
            generation_kw=gen_kw,
            load_kw=load_kw,
            grid_import_kw=grid_import_kw,
            grid_export_kw=grid_export_kw,
            energy_kwh=energy_kwh,
            battery_soc=battery_soc,
            source=TelemetrySource.IMPORT,
        )
