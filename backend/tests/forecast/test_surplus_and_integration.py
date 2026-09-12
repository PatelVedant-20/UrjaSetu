"""Forecast Surplus and Integration Tests.

Validates:
  12. surplus calculation integration
  13. persistence/retrieval integration where appropriate (forecast endpoints & surplus)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from .conftest import (
    ForecastPoint,
    ForecastProvider,
    ForecastRequest,
    ForecastResult,
    ForecastType,
)


def calculate_surplus(
    solar_points: list[ForecastPoint], load_points: list[ForecastPoint]
) -> list[dict[str, Any]]:
    """Domain rule: surplus = max(0, solar - load) for matching intervals."""
    load_map = {p.interval_start: p for p in load_points}
    surplus_points = []
    for s in solar_points:
        l = load_map.get(s.interval_start)
        load_kw = l.predicted_kw if l else Decimal("0")
        surplus_kw = max(Decimal("0"), s.predicted_kw - load_kw)
        hours = Decimal(str(int((s.interval_end - s.interval_start).total_seconds()))) / Decimal("3600")
        surplus_kwh = surplus_kw * hours
        confidence = min(s.confidence, l.confidence if l else 1.0)
        surplus_points.append(
            {
                "interval_start": s.interval_start,
                "interval_end": s.interval_end,
                "surplus_kw": surplus_kw,
                "surplus_kwh": surplus_kwh,
                "confidence": confidence,
            }
        )
    return surplus_points


class TestSurplusCalculationIntegration:
    """Scenario 12: Surplus calculation integration."""

    def test_surplus_when_generation_exceeds_load(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
    ) -> None:
        """When generation > load, surplus is positive."""
        start, end = horizon_times
        high_solar_history = [
            {"generation_kw": 8.0, "load_kw": 2.0} for _ in range(8)
        ]
        low_load_history = [
            {"generation_kw": 0.0, "load_kw": 2.0} for _ in range(8)
        ]

        solar_res = reference_provider.generate_forecast(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.SOLAR,
                horizon_start=start,
                horizon_end=end,
                historical_readings=high_solar_history,
            )
        )
        load_res = reference_provider.generate_forecast(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.LOAD,
                horizon_start=start,
                horizon_end=end,
                historical_readings=low_load_history,
            )
        )

        surplus = calculate_surplus(solar_res.points, load_res.points)
        assert len(surplus) > 0
        for sp in surplus:
            assert sp["surplus_kw"] == Decimal("6.0"), "Expected 8.0 kW solar - 2.0 kW load = 6.0 kW surplus"
            assert sp["surplus_kw"] >= Decimal("0")

    def test_surplus_when_load_exceeds_generation_is_zero(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
    ) -> None:
        """When load > generation (nighttime/high consumption), surplus is strictly zero."""
        start, end = horizon_times
        night_solar_history = [
            {"generation_kw": 0.0, "load_kw": 3.0} for _ in range(8)
        ]
        load_history = [
            {"generation_kw": 0.0, "load_kw": 3.0} for _ in range(8)
        ]

        solar_res = reference_provider.generate_forecast(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.SOLAR,
                horizon_start=start,
                horizon_end=end,
                historical_readings=night_solar_history,
            )
        )
        load_res = reference_provider.generate_forecast(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.LOAD,
                horizon_start=start,
                horizon_end=end,
                historical_readings=load_history,
            )
        )

        surplus = calculate_surplus(solar_res.points, load_res.points)
        for sp in surplus:
            assert sp["surplus_kw"] == Decimal("0"), "Deficit must yield 0 surplus, never negative"


class TestForecastingAPIIntegration:
    """Scenario 13: Persistence / API retrieval integration per docs/05_API_SPEC.md."""

    def test_create_forecast_run_endpoint(
        self, forecast_client: TestClient, sample_site_id: uuid.UUID
    ) -> None:
        """POST /api/v1/forecasts/runs triggers a forecast run."""
        payload = {
            "site_id": str(sample_site_id),
            "forecast_type": "solar",
            "horizon_start": "2026-03-16T00:00:00Z",
            "horizon_end": "2026-03-17T00:00:00Z",
        }
        response = forecast_client.post("/api/v1/forecasts/runs", json=payload)
        assert response.status_code in (200, 201, 202), (
            f"Expected 200/201/202 on POST /forecasts/runs, got {response.status_code}: {response.text}"
        )

    def test_get_site_forecasts_endpoint(
        self, forecast_client: TestClient, sample_site_id: uuid.UUID
    ) -> None:
        """GET /api/v1/sites/{site_id}/forecasts returns forecast points."""
        response = forecast_client.get(f"/api/v1/sites/{sample_site_id}/forecasts")
        assert response.status_code == 200, (
            f"Expected 200 on GET /sites/{sample_site_id}/forecasts, got {response.status_code}: {response.text}"
        )

    def test_get_site_surplus_endpoint(
        self, forecast_client: TestClient, sample_site_id: uuid.UUID
    ) -> None:
        """GET /api/v1/sites/{site_id}/surplus returns available surplus for a window."""
        url = (
            f"/api/v1/sites/{sample_site_id}/surplus?"
            f"start=2026-03-16T00:00:00Z&end=2026-03-17T00:00:00Z"
        )
        response = forecast_client.get(url)
        assert response.status_code == 200, (
            f"Expected 200 on GET /sites/{sample_site_id}/surplus, got {response.status_code}: {response.text}"
        )

    def test_nonexistent_site_surplus_returns_404(
        self, forecast_client: TestClient
    ) -> None:
        """GET /sites/{unknown_id}/surplus returns 404 with error envelope."""
        unknown_id = str(uuid.uuid4())
        response = forecast_client.get(f"/api/v1/sites/{unknown_id}/surplus")
        assert response.status_code == 404, (
            f"Expected 404 for unknown site surplus, got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "request_id" in body["error"]
