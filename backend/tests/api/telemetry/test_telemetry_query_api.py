"""Telemetry Query API tests.

Tests the query interface according to docs/05_API_SPEC.md:
  - GET /api/v1/sites/{site_id}/telemetry
  - GET /api/v1/sites/{site_id}/telemetry/latest

Covers required scenarios:
  3. latest reading
  4. interval query
  5. empty interval
  6. invalid site
  15. multiple sites isolation
  16. multiple readings at different timestamps
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient


def _as_instant(value: str) -> datetime:
    """Parse an API timestamp, accepting either `Z` or an explicit offset."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TestLatestReadingQuery:
    """Scenario 3: Latest valid reading and quality metadata."""

    def test_get_latest_reading_success(
        self,
        telemetry_client: TestClient,
        sample_site_id: str,
        make_batch_payloads: Callable[[int], list[dict[str, Any]]],
    ) -> None:
        """GET /sites/{site_id}/telemetry/latest returns the most recent reading."""
        readings = make_batch_payloads(4)
        ingest_resp = telemetry_client.post(
            "/api/v1/telemetry/readings/batch", json={"readings": readings}
        )
        assert ingest_resp.status_code in (
            200,
            201,
        ), f"Batch ingest failed with {ingest_resp.status_code}: {ingest_resp.text}"

        response = telemetry_client.get(f"/api/v1/sites/{sample_site_id}/telemetry/latest")
        assert response.status_code == 200, (
            f"Expected 200 on /sites/{sample_site_id}/telemetry/latest, got "
            f"{response.status_code}: {response.text}"
        )
        data = response.json()
        assert "timestamp" in data, "Reading must contain timestamp"
        assert "quality_status" in data, "Reading must contain quality_status"
        latest_expected_ts = readings[-1]["timestamp"]
        assert (
            data["timestamp"] >= latest_expected_ts
        ), f"Expected latest timestamp >= {latest_expected_ts}, got {data['timestamp']}"


class TestIntervalQuery:
    """Scenario 4: Interval time-series query."""

    def test_interval_query_bounded(
        self,
        telemetry_client: TestClient,
        sample_site_id: str,
        make_batch_payloads: Callable[[int], list[dict[str, Any]]],
    ) -> None:
        """GET /sites/{site_id}/telemetry returns normalized readings within [start, end]."""
        readings = make_batch_payloads(4)
        ingest_resp = telemetry_client.post(
            "/api/v1/telemetry/readings/batch", json={"readings": readings}
        )
        assert ingest_resp.status_code in (
            200,
            201,
        ), f"Batch ingest failed with {ingest_resp.status_code}: {ingest_resp.text}"

        start = readings[1]["timestamp"]
        end = readings[2]["timestamp"]
        url = f"/api/v1/sites/{sample_site_id}/telemetry?start={start}&end={end}&resolution=15m"
        response = telemetry_client.get(url)

        assert (
            response.status_code == 200
        ), f"Expected 200 on interval query, got {response.status_code}: {response.text}"
        data = response.json()
        items = data if isinstance(data, list) else data.get("readings", data.get("data", []))
        assert len(items) > 0, "Expected interval readings to be returned"
        for item in items:
            assert (
                start <= item["timestamp"] <= end
            ), f"Reading timestamp {item['timestamp']} out of requested interval [{start}, {end}]"


class TestEmptyIntervalQuery:
    """Scenario 5: Empty interval returns empty collection, not 404 or error."""

    def test_empty_interval_returns_200_empty(
        self, telemetry_client: TestClient, sample_site_id: str
    ) -> None:
        """Querying an interval with no data must return 200 with an empty list."""
        past_start = "2020-01-01T00:00:00Z"
        past_end = "2020-01-01T01:00:00Z"
        url = f"/api/v1/sites/{sample_site_id}/telemetry?start={past_start}&end={past_end}"
        response = telemetry_client.get(url)

        assert (
            response.status_code == 200
        ), f"Expected 200 on empty interval query, got {response.status_code}: {response.text}"
        data = response.json()
        items = data if isinstance(data, list) else data.get("readings", data.get("data", []))
        assert len(items) == 0, f"Expected 0 readings for empty interval, got {len(items)}"


class TestInvalidSite:
    """Scenario 6: Querying a non-existent site.

    Returns 404 with the locked error envelope.
    """

    def test_nonexistent_site_telemetry_returns_404(self, telemetry_client: TestClient) -> None:
        """GET /sites/{unknown_id}/telemetry must return 404 with error envelope."""
        unknown_site = str(uuid.uuid4())
        response = telemetry_client.get(f"/api/v1/sites/{unknown_site}/telemetry")

        assert (
            response.status_code == 404
        ), f"Expected 404 for non-existent site, got {response.status_code}: {response.text}"
        body = response.json()
        assert "error" in body, "Must follow locked error envelope"
        assert "code" in body["error"]
        assert "request_id" in body["error"]
        # Code should indicate resource not found specifically, not generic missing route
        assert body["error"]["code"] in ("SITE_NOT_FOUND", "NOT_FOUND")

    def test_nonexistent_site_latest_returns_404(self, telemetry_client: TestClient) -> None:
        """GET /sites/{unknown_id}/telemetry/latest must return 404 with error envelope."""
        unknown_site = str(uuid.uuid4())
        response = telemetry_client.get(f"/api/v1/sites/{unknown_site}/telemetry/latest")

        assert (
            response.status_code == 404
        ), f"Expected 404 for non-existent site, got {response.status_code}: {response.text}"
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] in ("SITE_NOT_FOUND", "NOT_FOUND")


class TestMultipleSitesIsolation:
    """Scenario 15: Multiple sites data isolation."""

    def test_readings_isolated_by_site(
        self,
        telemetry_client: TestClient,
        sample_meter_id: str,
        make_reading_payload: Callable[..., dict[str, Any]],
    ) -> None:
        """Site A query must not leak Site B telemetry."""
        site_a = "40000000-0000-0000-0000-000000000001"
        site_b = "40000000-0000-0000-0000-000000000002"

        t_now = datetime.now(UTC).isoformat()
        reading_a = make_reading_payload(site_id=site_a, meter_id=sample_meter_id, timestamp=t_now)
        reading_b = make_reading_payload(
            site_id=site_b,
            meter_id="50000000-0000-0000-0000-000000000002",
            timestamp=t_now,
            generation_kw=9.9,
        )

        r_a = telemetry_client.post("/api/v1/telemetry/readings", json=reading_a)
        assert r_a.status_code in (200, 201), f"Ingest for site A failed: {r_a.text}"

        r_b = telemetry_client.post("/api/v1/telemetry/readings", json=reading_b)
        assert r_b.status_code in (200, 201), f"Ingest for site B failed: {r_b.text}"

        resp_a = telemetry_client.get(f"/api/v1/sites/{site_a}/telemetry/latest")
        assert resp_a.status_code == 200, f"Query site A failed: {resp_a.text}"
        data_a = resp_a.json()
        assert data_a.get("site_id", site_a) == site_a
        assert float(data_a.get("generation_kw", 0)) != 9.9, "Site A query leaked Site B data"


class TestMultipleReadingsDifferentTimestamps:
    """Scenario 16: Multiple readings at different timestamps returned in order."""

    def test_chronological_ordering(
        self,
        telemetry_client: TestClient,
        sample_site_id: str,
        make_batch_payloads: Callable[[int], list[dict[str, Any]]],
    ) -> None:
        """Multiple readings ingested must be returned in strict chronological order."""
        batch = make_batch_payloads(5)
        ingest_resp = telemetry_client.post(
            "/api/v1/telemetry/readings/batch", json={"readings": batch}
        )
        assert ingest_resp.status_code in (200, 201), f"Batch ingest failed: {ingest_resp.text}"

        start = batch[0]["timestamp"]
        end = batch[-1]["timestamp"]
        resp = telemetry_client.get(
            f"/api/v1/sites/{sample_site_id}/telemetry?start={start}&end={end}"
        )
        assert resp.status_code == 200, f"Interval query failed: {resp.text}"
        data = resp.json()
        items = data if isinstance(data, list) else data.get("readings", data.get("data", []))
        timestamps = [r["timestamp"] for r in items]
        assert len(timestamps) >= 5, f"Expected 5 readings, got {len(timestamps)}"
        assert timestamps == sorted(timestamps), "Readings must be sorted chronologically"
