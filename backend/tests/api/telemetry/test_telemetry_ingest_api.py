"""Telemetry Ingestion API tests.

Tests the public ingestion interface according to docs/05_API_SPEC.md:
  - POST /api/v1/telemetry/readings
  - POST /api/v1/telemetry/readings/batch

Covers required scenarios:
  1. single telemetry ingest
  2. batch telemetry ingest
  7. invalid asset/meter
  8. malformed timestamp
  9. invalid units / physics validation
  10. missing required value
  11. duplicate reading
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient


class TestSingleTelemetryIngest:
    """Scenario 1: Single telemetry reading ingestion."""

    def test_single_telemetry_ingest_success(
        self, telemetry_client: TestClient, make_reading_payload: Callable[..., dict[str, Any]]
    ) -> None:
        """Valid normalized meter reading is accepted and persisted with quality metadata."""
        payload = make_reading_payload()
        response = telemetry_client.post("/api/v1/telemetry/readings", json=payload)

        assert response.status_code in (200, 201), (
            f"Expected 200 or 201 on valid single telemetry ingest, got {response.status_code}: "
            f"{response.text}"
        )
        data = response.json()
        assert "id" in data, "Ingested reading must have an identifier"
        assert data.get("meter_id") == payload["meter_id"]
        assert float(data.get("generation_kw", 0)) == pytest.approx(payload["generation_kw"])
        assert float(data.get("load_kw", 0)) == pytest.approx(payload["load_kw"])
        assert data.get("quality_status") in (
            "valid",
            "missing",
            "stale",
            "out_of_order",
            "duplicate",
            "invalid_value",
            "source_unavailable",
        ), (
            f"quality_status must be a recognized domain quality flag, got: "
            f"{data.get('quality_status')}"
        )


class TestBatchTelemetryIngest:
    """Scenario 2: Batch telemetry readings ingestion."""

    def test_batch_telemetry_ingest_success(
        self,
        telemetry_client: TestClient,
        make_batch_payloads: Callable[[int], list[dict[str, Any]]],
    ) -> None:
        """Batch of consecutive 15-minute readings is accepted."""
        readings = make_batch_payloads(4)
        payload = {"readings": readings}
        response = telemetry_client.post("/api/v1/telemetry/readings/batch", json=payload)

        assert response.status_code in (
            200,
            201,
        ), f"Expected 200 or 201 on batch ingest, got {response.status_code}: {response.text}"
        data = response.json()
        if isinstance(data, dict):
            assert data.get("ingested") == 4 or len(data.get("readings", [])) == 4
        elif isinstance(data, list):
            assert len(data) == 4
        else:
            pytest.fail(f"Unexpected response format from batch ingest: {type(data)}")


class TestInvalidAssetOrMeter:
    """Scenario 7: Ingestion with invalid or unknown asset/meter references."""

    def test_unknown_meter_id_rejected(
        self, telemetry_client: TestClient, make_reading_payload: Callable[..., dict[str, Any]]
    ) -> None:
        """Non-existent meter_id must return client error with locked error envelope."""
        non_existent_meter = str(uuid.uuid4())
        payload = make_reading_payload(meter_id=non_existent_meter)
        response = telemetry_client.post("/api/v1/telemetry/readings", json=payload)

        # Must reject with 400, 404, or 422 specific to the unknown meter (not an unrouted 404)
        assert response.status_code in (400, 404, 422), (
            f"Expected 400, 404, or 422 for non-existent meter_id, got {response.status_code}: "
            f"{response.text}"
        )
        body = response.json()
        assert "error" in body, "Non-2xx response must conform to locked error envelope"
        assert "code" in body["error"]
        assert "request_id" in body["error"]
        # Ensure it is not a generic FastAPI 404 "Not Found" for missing route
        assert body["error"]["message"] != "Not Found", (
            "Endpoint /api/v1/telemetry/readings returned generic 404 'Not Found' instead of "
            "domain validation"
        )


class TestMalformedTimestamp:
    """Scenario 8: Malformed timestamp rejected."""

    def test_malformed_timestamp_returns_422(
        self, telemetry_client: TestClient, make_reading_payload: Callable[..., dict[str, Any]]
    ) -> None:
        """Unparseable or non-ISO timestamp string must be rejected with 422."""
        payload = make_reading_payload(timestamp="invalid-timestamp-2026-99-99")
        response = telemetry_client.post("/api/v1/telemetry/readings", json=payload)

        assert response.status_code == 422, (
            f"Expected 422 Unprocessable Entity for malformed timestamp, got "
            f"{response.status_code}: {response.text}"
        )
        body = response.json()
        assert "error" in body or "detail" in body


class TestInvalidUnitsAndPhysics:
    """Scenario 9: Invalid units and physics boundary checks."""

    def test_negative_generation_rejected_or_flagged_suspect(
        self, telemetry_client: TestClient, make_reading_payload: Callable[..., dict[str, Any]]
    ) -> None:
        """Negative solar generation violates physical laws.

        It must be rejected, or accepted and flagged.
        """
        payload = make_reading_payload(generation_kw=-5.0)
        response = telemetry_client.post("/api/v1/telemetry/readings", json=payload)

        assert (
            response.status_code != 404
        ), f"Endpoint /api/v1/telemetry/readings returned 404 Not Found: {response.text}"
        if response.status_code in (400, 422):
            assert "error" in response.json() or "detail" in response.json()
        elif response.status_code in (200, 201):
            data = response.json()
            assert data.get("quality_status") == "invalid_value", (
                "If negative generation is accepted it must be flagged "
                "`invalid_value` — the locked state for a physically "
                "impossible measurement (docs/04_DATA_MODEL.md entity 10)."
            )
        else:
            pytest.fail(f"Unexpected status for negative generation: {response.status_code}")

    def test_battery_soc_out_of_bounds_rejected(
        self, telemetry_client: TestClient, make_reading_payload: Callable[..., dict[str, Any]]
    ) -> None:
        """Battery State of Charge must be in [0, 100]% range."""
        payload = make_reading_payload(battery_soc=125.0)
        response = telemetry_client.post("/api/v1/telemetry/readings", json=payload)

        assert response.status_code in (400, 422), (
            f"Expected 400 or 422 for battery_soc > 100%, got {response.status_code}: "
            f"{response.text}"
        )


class TestMissingRequiredValues:
    """Scenario 10: Missing required values."""

    def test_missing_meter_id_rejected(
        self, telemetry_client: TestClient, make_reading_payload: Callable[..., dict[str, Any]]
    ) -> None:
        """Payload without meter_id must return 422."""
        payload = make_reading_payload()
        payload.pop("meter_id", None)
        response = telemetry_client.post("/api/v1/telemetry/readings", json=payload)

        assert (
            response.status_code == 422
        ), f"Expected 422 for missing meter_id, got {response.status_code}: {response.text}"

    def test_empty_payload_rejected(self, telemetry_client: TestClient) -> None:
        """Empty JSON object must return 422."""
        response = telemetry_client.post("/api/v1/telemetry/readings", json={})
        assert (
            response.status_code == 422
        ), f"Expected 422 for empty body, got {response.status_code}: {response.text}"


class TestDuplicateReading:
    """Scenario 11: Duplicate reading handling."""

    def test_duplicate_reading_handling(
        self, telemetry_client: TestClient, make_reading_payload: Callable[..., dict[str, Any]]
    ) -> None:
        """Ingesting reading with identical (meter_id, timestamp) must be idempotent or flagged."""
        payload = make_reading_payload()
        resp1 = telemetry_client.post("/api/v1/telemetry/readings", json=payload)
        assert resp1.status_code in (
            200,
            201,
        ), f"Initial ingest failed ({resp1.status_code}): {resp1.text}"

        resp2 = telemetry_client.post("/api/v1/telemetry/readings", json=payload)
        assert resp2.status_code in (
            200,
            201,
            409,
        ), f"Duplicate reading returned unexpected status: {resp2.status_code}"
        if resp2.status_code in (200, 201):
            data = resp2.json()
            assert data.get("quality_status") in ("valid", "duplicate")
