"""Loader utility for Phase 3 forecast evaluation datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def get_forecast_fixtures_dir() -> Path:
    """Resolve the absolute path to the forecast synthetic data directory."""
    # Matches data/synthetic/forecast relative to the repository root
    base = Path(__file__).resolve()
    # Path navigation: backend/tests/fixtures/forecast/loader.py -> repo root
    repo_root = base.parents[4]
    fixtures_dir = repo_root / "data" / "synthetic" / "forecast"
    if not fixtures_dir.exists():
        raise FileNotFoundError(f"Forecast data directory not found at: {fixtures_dir}")
    return fixtures_dir


def load_forecast_manifest() -> dict[str, Any]:
    """Load the master forecast manifest."""
    manifest_path = get_forecast_fixtures_dir() / "forecast_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def list_available_forecast_scenarios() -> list[str]:
    """Return list of available scenario identifiers."""
    manifest = load_forecast_manifest()
    return list(manifest.get("scenarios", {}).keys())


def load_forecast_scenario(scenario_name: str) -> dict[str, Any]:
    """Load a specific scenario JSON dataset."""
    filename = scenario_name if scenario_name.endswith(".json") else f"{scenario_name}.json"
    scenario_path = get_forecast_fixtures_dir() / filename
    if not scenario_path.exists():
        available = list_available_forecast_scenarios()
        raise FileNotFoundError(
            f"Scenario fixture '{scenario_name}' not found at {scenario_path}. "
            f"Available: {available}"
        )
    with open(scenario_path, encoding="utf-8") as f:
        return json.load(f)


def extract_evaluation_vectors(
    scenario_name: str,
    skip_missing: bool = True,
) -> tuple[list[float], list[float], dict[str, Any]]:
    """Extract aligned (actuals, predictions, metadata) for a given scenario.

    Parameters
    ----------
    scenario_name : str
        Name of the scenario file or ID.
    skip_missing : bool, default True
        If True, skips intervals where actual telemetry is marked missing or None.

    Returns
    -------
    tuple[list[float], list[float], dict[str, Any]]
        (actual_kw_list, predicted_kw_list, scenario_metadata)
    """
    data = load_forecast_scenario(scenario_name)
    forecast_type = data.get("forecast_type", "solar")

    actual_points = data.get("actual_readings", [])
    forecast_points = data.get("forecast_points", [])

    actual_by_start: dict[str, Any] = {pt["interval_start"]: pt for pt in actual_points}

    actuals: list[float] = []
    predictions: list[float] = []

    for f_pt in forecast_points:
        start = f_pt["interval_start"]
        a_pt = actual_by_start.get(start)

        if not a_pt:
            continue

        # Extract measured value depending on forecast type
        if forecast_type == "solar":
            actual_val = a_pt.get("generation_kw")
        elif forecast_type == "load":
            actual_val = a_pt.get("load_kw")
        else:
            # surplus or net
            gen = a_pt.get("generation_kw") or 0.0
            load = a_pt.get("load_kw") or 0.0
            actual_val = max(0.0, gen - load)

        if actual_val is None or a_pt.get("quality_status") == "missing":
            if skip_missing:
                continue
            actual_val = 0.0

        actuals.append(float(actual_val))
        predictions.append(float(f_pt["predicted_kw"]))

    metadata = {
        "scenario_id": data.get("_scenario_id"),
        "title": data.get("title"),
        "forecast_type": forecast_type,
        "site_id": data.get("site_id"),
        "asset_capacity_kw": data.get("asset_capacity_kw"),
        "total_intervals": len(forecast_points),
        "evaluated_intervals": len(actuals),
    }

    return actuals, predictions, metadata
