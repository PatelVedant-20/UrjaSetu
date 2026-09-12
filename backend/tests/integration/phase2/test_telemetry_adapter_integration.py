"""Phase 2 Integration tests for Telemetry Adapter and Community Ingestion boundary."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.adapters.meter import (
    MeterSimulatorAdapter,
    NormalizedTelemetryBatch,
    NormalizedTelemetryReading,
    TelemetryIngestionProtocol,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"


class MockTelemetryService(TelemetryIngestionProtocol):
    """Mock downstream service implementing TelemetryIngestionProtocol.

    Verifies that Yagnik's future TelemetryService can seamlessly receive
    the normalized telemetry batch without any knowledge of raw CSV/data formats.
    """

    def __init__(self) -> None:
        self.ingested_readings: list[NormalizedTelemetryReading] = []

    def ingest_normalized_readings(
        self,
        readings: list[NormalizedTelemetryReading],
    ) -> int:
        self.ingested_readings.extend(readings)
        return len(readings)


def test_community_seed_meters_telemetry_simulation() -> None:
    """Test simulating telemetry for all synthetic meters defined in Phase 1 community seed."""
    meters_file = SYNTHETIC_DIR / "meters.json"
    assets_file = SYNTHETIC_DIR / "energy_assets.json"

    assert meters_file.is_file(), "meters.json fixture missing"

    with open(meters_file, encoding="utf-8") as f:
        meters_json = json.load(f)
        meters_data = (
            meters_json.get("meters", meters_json) if isinstance(meters_json, dict) else meters_json
        )

    with open(assets_file, encoding="utf-8") as f:
        assets_json = json.load(f)
        assets_data = (
            assets_json.get("energy_assets", assets_json)
            if isinstance(assets_json, dict)
            else assets_json
        )

    # Build lookup maps
    site_assets: dict[str, str] = {
        asset["site_id"]: asset["id"]
        for asset in assets_data
        if isinstance(asset, dict) and asset.get("asset_type") == "pv"
    }

    mock_service = MockTelemetryService()
    adapter = MeterSimulatorAdapter(seed=42)

    start = datetime(2026, 9, 12, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 12, 4, 0, 0, tzinfo=UTC)  # 4 hours = 16 intervals

    total_readings_generated = 0

    for meter in meters_data:
        meter_id = UUID(meter["id"])
        site_id = UUID(meter["site_id"])
        asset_id_str = site_assets.get(str(site_id))
        asset_id = UUID(asset_id_str) if asset_id_str else None

        batch: NormalizedTelemetryBatch = adapter.generate_synthetic(
            meter_id=meter_id,
            site_id=site_id,
            energy_asset_id=asset_id,
            start_time=start,
            end_time=end,
            interval_minutes=15,
            profile_type="residential_prosumer" if asset_id else "residential_consumer",
        )

        assert len(batch.readings) == 16
        total_readings_generated += len(batch.readings)

        # Stream to mock service in batches of 10
        for chunk in MeterSimulatorAdapter.stream_batches(batch.readings, batch_size=10):
            mock_service.ingest_normalized_readings(chunk)

    assert len(mock_service.ingested_readings) == total_readings_generated
    assert total_readings_generated == len(meters_data) * 16

    # Verify canonical contract properties on all ingested readings
    for r in mock_service.ingested_readings:
        assert isinstance(r.meter_id, UUID)
        assert r.timestamp.tzinfo is not None
        assert r.interval_start < r.interval_end
        assert r.generation_kw >= 0
        assert r.load_kw >= 0
        assert r.grid_import_kw >= 0
        assert r.grid_export_kw >= 0
