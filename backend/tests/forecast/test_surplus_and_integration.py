"""Forecast Surplus and Integration Tests.

Validates:
  12. surplus calculation integration
  13. persistence/retrieval integration where appropriate (forecast endpoints & surplus)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.domain.interfaces.forecasting import ForecastResult, HistoricalObservation
from app.domain.policies.surplus import SurplusWindow, calculate_surplus

from .conftest import (
    ForecastProvider,
    ForecastRequest,
    ForecastType,
)


def _history(generation_kw: float, load_kw: float, count: int = 8) -> list[HistoricalObservation]:
    """A flat history at the given levels, in the canonical contract's shape."""
    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    return [
        HistoricalObservation(
            interval_start=base + timedelta(minutes=15 * i),
            interval_end=base + timedelta(minutes=15 * (i + 1)),
            generation_kw=Decimal(str(generation_kw)),
            load_kw=Decimal(str(load_kw)),
        )
        for i in range(count)
    ]


def _surplus_from(solar: ForecastResult, load: ForecastResult) -> SurplusWindow:
    """Pair two forecasts using the canonical domain policy.

    This test used to carry its own `calculate_surplus`, which meant it proved
    that a copy of the rule worked rather than the rule the platform actually
    applies. There is one surplus implementation, in
    `app.domain.policies.surplus`.
    """
    return calculate_surplus(
        generation=[(p.interval_start, p.interval_end, p.predicted_kw) for p in solar.points],
        consumption=[(p.interval_start, p.interval_end, p.predicted_kw) for p in load.points],
    )


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
        high_solar_history = _history(generation_kw=8.0, load_kw=2.0)
        low_load_history = _history(generation_kw=0.0, load_kw=2.0)

        solar_res = reference_provider.predict(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.SOLAR,
                horizon_start=start,
                horizon_end=end,
                history=high_solar_history,
                interval=timedelta(minutes=15),
            )
        )
        load_res = reference_provider.predict(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.LOAD,
                horizon_start=start,
                horizon_end=end,
                history=low_load_history,
                interval=timedelta(minutes=15),
            )
        )

        window = _surplus_from(solar_res, load_res)

        assert window.points
        for point in window.points:
            assert point.surplus_kw == Decimal(
                "6.000"
            ), "Expected 8.0 kW solar - 2.0 kW load = 6.0 kW surplus"
            assert point.exportable_kw == Decimal("6.000")
        assert window.has_exportable_energy is True

    def test_surplus_when_load_exceeds_generation_is_zero(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
    ) -> None:
        """When load > generation (nighttime/high consumption), surplus is strictly zero."""
        start, end = horizon_times
        night_solar_history = _history(generation_kw=0.0, load_kw=3.0)
        load_history = _history(generation_kw=0.0, load_kw=3.0)

        solar_res = reference_provider.predict(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.SOLAR,
                horizon_start=start,
                horizon_end=end,
                history=night_solar_history,
                interval=timedelta(minutes=15),
            )
        )
        load_res = reference_provider.predict(
            ForecastRequest(
                site_id=sample_site_id,
                forecast_type=ForecastType.LOAD,
                horizon_start=start,
                horizon_end=end,
                history=load_history,
                interval=timedelta(minutes=15),
            )
        )

        window = _surplus_from(solar_res, load_res)

        for point in window.points:
            # The signed surplus keeps the deficit; what can be *sold* is zero.
            assert point.surplus_kw is not None
            assert point.surplus_kw <= Decimal("0")
            assert point.exportable_kw == Decimal(
                "0"
            ), "A deficit must never present as sellable energy"
        assert window.has_exportable_energy is False


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
            "Expected 200/201/202 on POST /forecasts/runs, got "
            f"{response.status_code}: {response.text}"
        )

    def test_get_site_forecasts_endpoint(
        self, forecast_client: TestClient, sample_site_id: uuid.UUID
    ) -> None:
        """GET /api/v1/sites/{site_id}/forecasts returns forecast points."""
        response = forecast_client.get(f"/api/v1/sites/{sample_site_id}/forecasts")
        assert response.status_code == 200, (
            f"Expected 200 on GET /sites/{sample_site_id}/forecasts, got "
            f"{response.status_code}: {response.text}"
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
            f"Expected 200 on GET /sites/{sample_site_id}/surplus, got "
            f"{response.status_code}: {response.text}"
        )

    def test_nonexistent_site_surplus_returns_404(self, forecast_client: TestClient) -> None:
        """GET /sites/{unknown_id}/surplus returns 404 with error envelope."""
        unknown_id = str(uuid.uuid4())
        response = forecast_client.get(f"/api/v1/sites/{unknown_id}/surplus")
        assert (
            response.status_code == 404
        ), f"Expected 404 for unknown site surplus, got {response.status_code}: {response.text}"
        body = response.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "request_id" in body["error"]
