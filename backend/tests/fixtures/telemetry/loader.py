"""Telemetry fixture loader for UrjaSetu Phase 2.

Provides deterministic, schema-compliant loading of synthetic telemetry
data-quality fixtures located under data/synthetic/telemetry/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Path resolution: backend/tests/fixtures/telemetry/loader.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
TELEMETRY_DATA_DIR = REPO_ROOT / "data" / "synthetic" / "telemetry"

SCENARIO_FILES = {
    "valid": "valid_telemetry.json",
    "missing": "missing_telemetry.json",
    "stale": "stale_telemetry.json",
    "out_of_order": "out_of_order_telemetry.json",
    "duplicate": "duplicate_telemetry.json",
    "invalid_measurement": "invalid_measurement_telemetry.json",
}


def get_telemetry_fixtures_dir() -> Path:
    """Return the absolute path to the synthetic telemetry fixtures directory."""
    return TELEMETRY_DATA_DIR


def list_available_scenarios() -> list[str]:
    """Return list of all recognized scenario names."""
    return sorted(SCENARIO_FILES.keys())


def load_telemetry_manifest() -> dict[str, Any]:
    """Load the master telemetry manifest describing all data quality scenarios."""
    manifest_path = TELEMETRY_DATA_DIR / "telemetry_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Telemetry manifest not found at: {manifest_path}")
    with manifest_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_telemetry_fixture(scenario: str) -> dict[str, Any]:
    """Load raw JSON fixture dict for a given scenario.

    Supported scenarios:
        - valid
        - missing
        - stale
        - out_of_order
        - duplicate
        - invalid_measurement
    """
    normalized_scenario = scenario.lower().strip()
    filename = SCENARIO_FILES.get(normalized_scenario)
    if not filename:
        valid_options = ", ".join(SCENARIO_FILES.keys())
        raise ValueError(
            f"Unknown telemetry scenario '{scenario}'. Available scenarios: {valid_options}"
        )

    file_path = TELEMETRY_DATA_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Telemetry fixture file not found at: {file_path}")

    with file_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_telemetry_readings(scenario: str) -> list[dict[str, Any]]:
    """Load only the list of telemetry readings for a given scenario."""
    fixture = load_telemetry_fixture(scenario)
    return fixture.get("readings", [])
