"""Telemetry Pipeline Integration Tests.

Validates the Phase-2 Gate:
  ingest -> store -> latest query -> interval query -> quality status

Covers required scenarios:
  12. out-of-order reading
  13. stale reading
  14. quality status
  Phase-2 gate end-to-end flow
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def telemetry_client() -> TestClient:
    app = create_app()
    with TestClient(app) as client:
        yield client


class TestTelemetryGatePipeline:
    """Phase-2 Gate: ingest -> store -> latest query -> interval query -> quality status."""

    def test_full_pipeline_ingest_store_query_quality(
        self, telemetry_client: TestClient
    ) -> None:
        """End-to-end Phase 2 gate verification."""
        site_id = "40000000-0000-0000-0000-000000000001"
        meter_id = "50000000-0000-0000-0000-000000000001"

        t1 = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 15, 10, 15, 0, tzinfo=timezone.utc)

        reading_1 = {
            "meter_id": meter_id,
            "site_id": site_id,
            "timestamp": t1.isoformat(),
            "interval_start": (t1 - timedelta(minutes=15)).isoformat(),
            "interval_end": t1.isoformat(),
            "generation_kw": 5.0,
            "load_kw": 2.0,
            "grid_import_kw": 0.0,
            "grid_export_kw": 3.0,
            "energy_kwh": 1.25,
            "source": "smart_meter",
        }

        reading_2 = {
            "meter_id": meter_id,
            "site_id": site_id,
            "timestamp": t2.isoformat(),
            "interval_start": (t2 - timedelta(minutes=15)).isoformat(),
            "interval_end": t2.isoformat(),
            "generation_kw": 6.2,
            "load_kw": 2.1,
            "grid_import_kw": 0.0,
            "grid_export_kw": 4.1,
            "energy_kwh": 1.55,
            "source": "smart_meter",
        }

        # Step 1: Ingest
        resp_ingest_1 = telemetry_client.post("/api/v1/telemetry/readings", json=reading_1)
        assert resp_ingest_1.status_code in (200, 201), (
            f"Gate failure: ingest 1 failed ({resp_ingest_1.status_code}): {resp_ingest_1.text}"
        )

        resp_ingest_2 = telemetry_client.post("/api/v1/telemetry/readings", json=reading_2)
        assert resp_ingest_2.status_code in (200, 201), (
            f"Gate failure: ingest 2 failed ({resp_ingest_2.status_code}): {resp_ingest_2.text}"
        )

        # Step 2: Latest query
        resp_latest = telemetry_client.get(f"/api/v1/sites/{site_id}/telemetry/latest")
        assert resp_latest.status_code == 200, (
            f"Gate failure: latest query failed ({resp_latest.status_code}): {resp_latest.text}"
        )
        latest_data = resp_latest.json()
        assert latest_data["timestamp"] == t2.isoformat(), (
            f"Latest query must return reading with latest timestamp {t2.isoformat()}, got {latest_data.get('timestamp')}"
        )

        # Step 3: Quality status check
        assert "quality_status" in latest_data, "Gate failure: reading must include quality_status"
        assert latest_data["quality_status"] in ("valid", "suspect", "missing", "duplicate"), (
            f"Gate failure: unknown quality status {latest_data['quality_status']}"
        )

        # Step 4: Interval query
        query_url = (
            f"/api/v1/sites/{site_id}/telemetry?"
            f"start={(t1 - timedelta(minutes=15)).isoformat()}&end={t2.isoformat()}"
        )
        resp_interval = telemetry_client.get(query_url)
        assert resp_interval.status_code == 200, (
            f"Gate failure: interval query failed ({resp_interval.status_code}): {resp_interval.text}"
        )
        interval_data = resp_interval.json()
        records = (
            interval_data
            if isinstance(interval_data, list)
            else interval_data.get("readings", interval_data.get("data", []))
        )
        assert len(records) >= 2, f"Gate failure: expected at least 2 interval readings, got {len(records)}"


class TestOutOfOrderReading:
    """Scenario 12: Ingestion of out-of-order readings."""

    def test_out_of_order_ingestion_preserves_temporal_order(
        self, telemetry_client: TestClient
    ) -> None:
        """Ingesting reading T2 before reading T1 correctly orders data by timestamp."""
        site_id = "40000000-0000-0000-0000-000000000001"
        meter_id = "50000000-0000-0000-0000-000000000001"

        t_earlier = datetime(2026, 3, 15, 8, 0, 0, tzinfo=timezone.utc)
        t_later = datetime(2026, 3, 15, 8, 15, 0, tzinfo=timezone.utc)

        reading_later = {
            "meter_id": meter_id,
            "site_id": site_id,
            "timestamp": t_later.isoformat(),
            "generation_kw": 3.0,
            "load_kw": 1.0,
            "grid_import_kw": 0.0,
            "grid_export_kw": 2.0,
            "source": "smart_meter",
        }
        reading_earlier = {
            "meter_id": meter_id,
            "site_id": site_id,
            "timestamp": t_earlier.isoformat(),
            "generation_kw": 2.5,
            "load_kw": 1.0,
            "grid_import_kw": 0.0,
            "grid_export_kw": 1.5,
            "source": "smart_meter",
        }

        # Ingest later reading first
        r2 = telemetry_client.post("/api/v1/telemetry/readings", json=reading_later)
        assert r2.status_code in (200, 201), (
            f"Ingesting later reading failed ({r2.status_code}): {r2.text}"
        )

        # Ingest earlier reading second
        r1 = telemetry_client.post("/api/v1/telemetry/readings", json=reading_earlier)
        assert r1.status_code in (200, 201), (
            f"Ingesting earlier reading failed ({r1.status_code}): {r1.text}"
        )

        # Interval query must return [earlier, later] sorted chronologically
        query_url = (
            f"/api/v1/sites/{site_id}/telemetry?"
            f"start={t_earlier.isoformat()}&end={t_later.isoformat()}"
        )
        resp = telemetry_client.get(query_url)
        assert resp.status_code == 200, f"Interval query failed ({resp.status_code}): {resp.text}"
        records = resp.json() if isinstance(resp.json(), list) else resp.json().get("readings", [])
        assert len(records) >= 2, f"Expected 2 readings, got {len(records)}"
        assert records[0]["timestamp"] <= records[-1]["timestamp"], (
            "Interval query must be ordered chronologically regardless of ingestion order"
        )


class TestStaleReadingQuality:
    """Scenario 13: Stale reading detection."""

    def test_stale_reading_metadata(self, telemetry_client: TestClient) -> None:
        """Readings far in the past should be tracked and include quality metadata."""
        site_id = "40000000-0000-0000-0000-000000000001"
        meter_id = "50000000-0000-0000-0000-000000000001"

        t_stale = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        stale_reading = {
            "meter_id": meter_id,
            "site_id": site_id,
            "timestamp": t_stale,
            "generation_kw": 4.0,
            "load_kw": 2.0,
            "grid_import_kw": 0.0,
            "grid_export_kw": 2.0,
            "source": "smart_meter",
        }
        resp = telemetry_client.post("/api/v1/telemetry/readings", json=stale_reading)
        assert resp.status_code in (200, 201), (
            f"Stale reading ingest failed ({resp.status_code}): {resp.text}"
        )
        data = resp.json()
        assert "quality_status" in data, "Stale reading response must include quality_status"


class TestQualityStatusValidation:
    """Scenario 14: Quality status assignment adhering to Phase 2 domain rules."""

    def test_quality_status_enumeration(self, telemetry_client: TestClient) -> None:
        """quality_status must strictly belong to {valid, suspect, missing, duplicate}."""
        site_id = "40000000-0000-0000-0000-000000000001"
        meter_id = "50000000-0000-0000-0000-000000000001"
        t = datetime.now(timezone.utc).isoformat()

        reading = {
            "meter_id": meter_id,
            "site_id": site_id,
            "timestamp": t,
            "generation_kw": 3.5,
            "load_kw": 1.2,
            "grid_import_kw": 0.0,
            "grid_export_kw": 2.3,
            "source": "smart_meter",
        }
        resp = telemetry_client.post("/api/v1/telemetry/readings", json=reading)
        assert resp.status_code in (200, 201), (
            f"Reading ingest failed ({resp.status_code}): {resp.text}"
        )
        data = resp.json()
        assert data.get("quality_status") in ("valid", "suspect", "missing", "duplicate"), (
            f"Invalid quality_status flag: {data.get('quality_status')}"
        )
