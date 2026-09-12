"""Unit tests for import_telemetry.py script runner."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from scripts.import_telemetry import run_importer

SAMPLE_METER_ID = UUID("10000000-0000-0000-0000-000000000001")


def test_importer_synthetic_dry_run() -> None:
    batch = run_importer(
        synthetic=True,
        meter_id=SAMPLE_METER_ID,
        days=1,
        interval_minutes=15,
        seed=42,
        dry_run=True,
    )

    assert batch is not None
    assert len(batch.readings) == 96
    assert batch.total_records == 96


def test_importer_csv_file_and_export_json() -> None:
    with TemporaryDirectory() as tmpdir:
        csv_file = Path(tmpdir) / "test_data.csv"
        json_output = Path(tmpdir) / "output.json"

        csv_content = (
            "timestamp,meter_id,generation_kw,load_kw\n"
            "2026-09-12T08:00:00Z,10000000-0000-0000-0000-000000000001,2.5,1.0\n"
            "2026-09-12T08:15:00Z,10000000-0000-0000-0000-000000000001,3.0,1.2\n"
        )
        csv_file.write_text(csv_content, encoding="utf-8")

        batch = run_importer(
            csv_path=csv_file,
            dry_run=True,
            output_json=json_output,
        )

        assert len(batch.readings) == 2
        assert json_output.exists()

        with open(json_output, encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["meter_id"] == "10000000-0000-0000-0000-000000000001"
        assert data[0]["generation_kw"] == 2.5
        assert data[0]["load_kw"] == 1.0
