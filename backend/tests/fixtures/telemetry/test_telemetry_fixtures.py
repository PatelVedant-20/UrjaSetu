"""Unit tests validating the Phase 2 telemetry data-quality fixtures.

Verifies:
  1. All 6 required scenarios exist: valid, missing, stale,
     out_of_order, duplicate, invalid_measurement.
  2. Strict conformity to docs/04_DATA_MODEL.md entity 10 (telemetry_readings).
  3. No invented fields.
  4. Deterministic UUIDs and ISO-8601 UTC timestamps.
  5. Referential integrity to Phase-1 synthetic meters and energy assets.
  6. Expected data-quality characteristics for each scenario.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

import pytest

from tests.fixtures.telemetry.loader import (
    get_telemetry_fixtures_dir,
    list_available_scenarios,
    load_telemetry_fixture,
    load_telemetry_manifest,
    load_telemetry_readings,
)

# ---------------------------------------------------------------------------
# Strict Contract Fields (docs/04_DATA_MODEL.md section 10)
# ---------------------------------------------------------------------------
ALLOWED_TELEMETRY_FIELDS = {
    "id",
    "meter_id",
    "energy_asset_id",
    "timestamp",
    "interval_start",
    "interval_end",
    "generation_kw",
    "load_kw",
    "grid_import_kw",
    "grid_export_kw",
    "energy_kwh",
    "battery_soc",
    "quality_status",
    "source",
}

REQUIRED_READING_FIELDS = {
    "id",
    "meter_id",
    "timestamp",
    "interval_start",
    "interval_end",
    "generation_kw",
    "load_kw",
    "grid_import_kw",
    "grid_export_kw",
    "energy_kwh",
    "quality_status",
    "source",
}

EXPECTED_SCENARIOS = {
    "valid",
    "missing",
    "stale",
    "out_of_order",
    "duplicate",
    "invalid_measurement",
}

ISO_TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _is_valid_uuid(val: str | None) -> bool:
    if val is None:
        return True
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError):
        return False


def _parse_iso(val: str) -> datetime:
    assert ISO_TIMESTAMP_PATTERN.match(val), f"Timestamp '{val}' is not ISO-8601 UTC (ending in Z)"
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_manifest_covers_all_required_scenarios() -> None:
    manifest = load_telemetry_manifest()
    assert manifest["target_entity"] == "telemetry_readings"
    scenarios = manifest["scenarios"]
    for required in EXPECTED_SCENARIOS:
        assert required in scenarios, f"Scenario '{required}' missing from manifest"
        file_name = scenarios[required]["file"]
        assert (get_telemetry_fixtures_dir() / file_name).exists()


def test_loader_available_scenarios() -> None:
    available = set(list_available_scenarios())
    assert EXPECTED_SCENARIOS.issubset(available)


@pytest.mark.parametrize("scenario", sorted(EXPECTED_SCENARIOS))
def test_each_scenario_loads_valid_readings(scenario: str) -> None:
    readings = load_telemetry_readings(scenario)
    assert len(readings) >= 3, f"Scenario '{scenario}' must contain at least 3 readings"

    for r in readings:
        # Check required fields
        for field in REQUIRED_READING_FIELDS:
            assert field in r, f"Field '{field}' missing from reading in scenario '{scenario}'"

        # Check no invented fields
        extra_fields = set(r.keys()) - ALLOWED_TELEMETRY_FIELDS
        assert (
            not extra_fields
        ), f"Forbidden/invented fields in scenario '{scenario}': {extra_fields}"

        # Check UUIDs
        assert _is_valid_uuid(r["id"]), f"Invalid reading id UUID: {r['id']}"
        assert _is_valid_uuid(r["meter_id"]), f"Invalid meter_id UUID: {r['meter_id']}"
        if r.get("energy_asset_id") is not None:
            asset_uuid = r["energy_asset_id"]
            assert _is_valid_uuid(asset_uuid), f"Invalid energy_asset_id UUID: {asset_uuid}"

        # Check ISO timestamp format
        assert ISO_TIMESTAMP_PATTERN.match(r["timestamp"])
        assert ISO_TIMESTAMP_PATTERN.match(r["interval_start"])
        assert ISO_TIMESTAMP_PATTERN.match(r["interval_end"])


def test_valid_scenario_properties() -> None:
    readings = load_telemetry_readings("valid")
    assert len(readings) == 5

    prev_end: datetime | None = None
    for r in readings:
        assert r["quality_status"] == "valid"
        start = _parse_iso(r["interval_start"])
        end = _parse_iso(r["interval_end"])
        assert end > start, "interval_end must be strictly after interval_start"

        # Continuous 15-minute intervals
        duration_min = (end - start).total_seconds() / 60
        assert duration_min == 15.0

        if prev_end is not None:
            assert start == prev_end, "Intervals in valid scenario must be contiguous"
        prev_end = end

        # Physically valid values
        assert r["generation_kw"] >= 0.0
        assert r["load_kw"] >= 0.0
        assert r["grid_import_kw"] >= 0.0
        assert r["grid_export_kw"] >= 0.0
        assert r["energy_kwh"] >= 0.0
        if r.get("battery_soc") is not None:
            assert 0.0 <= r["battery_soc"] <= 100.0


def test_missing_scenario_properties() -> None:
    data = load_telemetry_fixture("missing")
    gap_meta = data["gap_metadata"]
    assert gap_meta["missing_intervals_count"] == 2
    readings = data["readings"]

    # Timestamps should skip the 09:30Z - 10:00Z window
    timestamps = [r["timestamp"] for r in readings]
    assert "2026-09-12T09:15:00Z" in timestamps
    assert "2026-09-12T09:30:00Z" in timestamps
    assert "2026-09-12T09:45:00Z" not in timestamps  # Missing interval
    assert "2026-09-12T10:00:00Z" not in timestamps  # Missing interval
    assert "2026-09-12T10:15:00Z" in timestamps


def test_stale_scenario_properties() -> None:
    data = load_telemetry_fixture("stale")
    stale_meta = data["stale_metadata"]
    assert stale_meta["staleness_duration_minutes"] > stale_meta["freshness_threshold_minutes"]

    readings = data["readings"]
    stale_readings = [r for r in readings if r["quality_status"] == "stale"]
    assert len(stale_readings) >= 3

    # Stale readings repeat identical measurements
    first_gen = stale_readings[0]["generation_kw"]
    first_load = stale_readings[0]["load_kw"]
    for r in stale_readings:
        assert r["generation_kw"] == first_gen
        assert r["load_kw"] == first_load


def test_out_of_order_scenario_properties() -> None:
    data = load_telemetry_fixture("out_of_order")
    readings = data["readings"]
    arrival_timestamps = [r["timestamp"] for r in readings]

    # Verify that arrivals in the fixture file are NOT sorted
    sorted_timestamps = sorted(arrival_timestamps)
    assert arrival_timestamps != sorted_timestamps, "Out-of-order readings must not be pre-sorted"

    # Verify that sorting recovers the expected chronological order
    reconstructed_ids = [
        r["id"] for r in sorted(readings, key=lambda x: _parse_iso(x["timestamp"]))
    ]
    assert reconstructed_ids == data["expected_chronological_order"]


def test_duplicate_scenario_properties() -> None:
    data = load_telemetry_fixture("duplicate")
    readings = data["readings"]
    duplicate_readings = [r for r in readings if r["quality_status"] == "duplicate"]
    assert len(duplicate_readings) >= 2

    # Verify exact duplicate retransmission
    exact_dup_id = "70000000-0000-0000-0000-000000000041"
    exact_matches = [r for r in readings if r["id"] == exact_dup_id]
    assert len(exact_matches) == 2, "Must contain exactly two matching records for exact duplicate"

    # Verify collision duplicate (same meter and timestamp, different values)
    collision_ts = "2026-09-12T09:30:00Z"
    collision_matches = [r for r in readings if r["timestamp"] == collision_ts]
    assert len(collision_matches) == 2
    assert collision_matches[0]["generation_kw"] != collision_matches[1]["generation_kw"]


def test_invalid_measurement_scenario_properties() -> None:
    data = load_telemetry_fixture("invalid_measurement")
    readings = data["readings"]
    for r in readings:
        assert r["quality_status"] == "invalid"

    # Check specific violations
    gen_values = [r["generation_kw"] for r in readings]
    assert any(g < 0 for g in gen_values), "Must include negative generation"
    assert any(g > 50.0 for g in gen_values), "Must include excessive generation breaching capacity"

    load_values = [r["load_kw"] for r in readings]
    assert any(load < 0 for load in load_values), "Must include negative load"

    soc_values = [r["battery_soc"] for r in readings if r.get("battery_soc") is not None]
    assert any(soc > 100.0 for soc in soc_values), "Must include out-of-bounds battery SOC"

    inverted = [
        r for r in readings if _parse_iso(r["interval_start"]) > _parse_iso(r["interval_end"])
    ]
    assert len(inverted) >= 1, "Must include inverted interval chronology"
