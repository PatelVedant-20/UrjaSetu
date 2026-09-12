"""Unit tests for TelemetryCSVAdapter."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.adapters.meter import (
    AdapterError,
    AdapterValidationError,
    TelemetryCSVAdapter,
)

SAMPLE_METER_ID = UUID("10000000-0000-0000-0000-000000000001")
SAMPLE_SITE_ID = UUID("20000000-0000-0000-0000-000000000001")
SAMPLE_ASSET_ID = UUID("30000000-0000-0000-0000-000000000001")


def test_valid_csv_parsing_all_columns() -> None:
    csv_text = (
        "timestamp,meter_id,site_id,energy_asset_id,generation_kw,load_kw,grid_import_kw,grid_export_kw,energy_kwh,voltage_pu,battery_soc\n"
        "2026-09-12T10:00:00Z,10000000-0000-0000-0000-000000000001,20000000-0000-0000-0000-000000000001,30000000-0000-0000-0000-000000000001,3.5,1.2,0.0,2.3,0.3,1.01,80.0\n"
        "2026-09-12T10:15:00Z,10000000-0000-0000-0000-000000000001,20000000-0000-0000-0000-000000000001,30000000-0000-0000-0000-000000000001,4.0,1.5,0.0,2.5,0.375,1.02,82.5\n"
    )
    adapter = TelemetryCSVAdapter()
    batch = adapter.parse_string(csv_text)

    assert len(batch.readings) == 2
    assert batch.total_records == 2
    assert len(batch.errors) == 0

    first = batch.readings[0]
    assert first.meter_id == SAMPLE_METER_ID
    assert first.energy_asset_id == SAMPLE_ASSET_ID
    assert first.timestamp == datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)
    assert first.interval_start == datetime(2026, 9, 12, 10, 0, 0, tzinfo=UTC)
    assert first.interval_end == datetime(2026, 9, 12, 10, 15, 0, tzinfo=UTC)
    assert first.generation_kw == Decimal("3.5")
    assert first.load_kw == Decimal("1.2")
    assert first.grid_import_kw == Decimal("0.0")
    assert first.grid_export_kw == Decimal("2.3")
    assert first.energy_kwh == Decimal("0.3")
    assert first.battery_soc == Decimal("80.0")


def test_valid_csv_header_synonyms_and_fallbacks() -> None:
    csv_text = "datetime,solar_kw,demand_kw\n" "2026-09-12 12:00:00,5.0,2.0\n"
    adapter = TelemetryCSVAdapter(
        default_meter_id=SAMPLE_METER_ID,
        default_site_id=SAMPLE_SITE_ID,
    )
    batch = adapter.parse_string(csv_text)

    assert len(batch.readings) == 1
    reading = batch.readings[0]
    assert reading.meter_id == SAMPLE_METER_ID
    assert reading.generation_kw == Decimal("5.0")
    assert reading.load_kw == Decimal("2.0")
    # Automatic derivation: load (2.0) - gen (5.0) -> export 3.0, import 0.0
    assert reading.grid_import_kw == Decimal("0.0")
    assert reading.grid_export_kw == Decimal("3.0")


def test_missing_timestamp_column() -> None:
    csv_text = "meter_id,generation_kw,load_kw\n" "10000000-0000-0000-0000-000000000001,3.0,1.0\n"
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterValidationError, match="Missing required timestamp column"):
        adapter.parse_string(csv_text)


def test_missing_meter_id_without_default() -> None:
    csv_text = "timestamp,generation_kw,load_kw\n" "2026-09-12T10:00:00Z,3.0,1.0\n"
    adapter = TelemetryCSVAdapter()  # No default_meter_id
    with pytest.raises(AdapterValidationError, match="Missing required UUID for field 'meter_id'"):
        adapter.parse_string(csv_text)


def test_invalid_timestamp_format() -> None:
    csv_text = (
        "timestamp,meter_id,generation_kw\n"
        "not-a-valid-date,10000000-0000-0000-0000-000000000001,3.0\n"
    )
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterValidationError, match="Invalid timestamp format"):
        adapter.parse_string(csv_text)


def test_invalid_numeric_values() -> None:
    csv_text = (
        "timestamp,meter_id,generation_kw\n"
        "2026-09-12T10:00:00Z,10000000-0000-0000-0000-000000000001,invalid_gen\n"
    )
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterValidationError, match="must be a valid number"):
        adapter.parse_string(csv_text)


def test_negative_generation_rejected() -> None:
    csv_text = (
        "timestamp,meter_id,generation_kw\n"
        "2026-09-12T10:00:00Z,10000000-0000-0000-0000-000000000001,-5.0\n"
    )
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterValidationError, match="cannot be negative"):
        adapter.parse_string(csv_text)


def test_invalid_battery_soc_rejected() -> None:
    csv_text = (
        "timestamp,meter_id,battery_soc\n"
        "2026-09-12T10:00:00Z,10000000-0000-0000-0000-000000000001,150.0\n"
    )
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterValidationError, match="battery_soc must be between 0.0 and 100.0"):
        adapter.parse_string(csv_text)


def test_empty_string_input() -> None:
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterValidationError, match="CSV input is empty"):
        adapter.parse_string("")

    with pytest.raises(AdapterValidationError, match="CSV input is empty"):
        adapter.parse_string("   \n\n  ")


def test_header_only_csv() -> None:
    csv_text = "timestamp,meter_id,generation_kw,load_kw\n"
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterValidationError, match="CSV input contains no data rows"):
        adapter.parse_string(csv_text)


def test_malformed_csv_syntax() -> None:
    # Unclosed quote
    csv_text = 'timestamp,meter_id\n"2026-09-12T10:00:00Z,10000000-0000-0000-0000-000000000001\n'
    adapter = TelemetryCSVAdapter()
    with pytest.raises(AdapterError):
        adapter.parse_string(csv_text)


def test_resilient_mode_skips_bad_rows() -> None:
    csv_text = (
        "timestamp,meter_id,generation_kw,load_kw\n"
        "2026-09-12T10:00:00Z,10000000-0000-0000-0000-000000000001,3.0,1.0\n"
        "2026-09-12T10:15:00Z,10000000-0000-0000-0000-000000000001,BAD_NUM,1.0\n"
        "2026-09-12T10:30:00Z,10000000-0000-0000-0000-000000000001,4.0,2.0\n"
    )
    adapter = TelemetryCSVAdapter(strict=False)
    batch = adapter.parse_string(csv_text)

    assert len(batch.readings) == 2
    assert batch.total_records == 3
    assert len(batch.errors) == 1
    assert "Line 3" in batch.errors[0]
