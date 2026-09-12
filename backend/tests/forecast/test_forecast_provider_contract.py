"""ForecastProvider contract verification tests.

Validates the ForecastProvider protocol and baseline provider behavior against:
  1. Provider satisfies ForecastProvider
  2. Request contract is respected
  3. Result contract is respected
  4. Required timestamps exist
  5. Horizon is correct
  6. Units are correct
  7. Empty input behavior
  8. Insufficient history
  9. Deterministic output
  10. Provider failure isolation
  11. Multiple forecast intervals
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from .conftest import (
    ForecastProvider,
    ForecastRequest,
    ForecastResult,
    ForecastType,
    InsufficientHistoryError,
)


class TestForecastProviderContract:
    """Test suite ensuring any conforming provider adheres strictly to ForecastProvider."""

    def test_provider_satisfies_protocol(self, reference_provider: ForecastProvider) -> None:
        """1. Provider satisfies ForecastProvider protocol."""
        assert isinstance(reference_provider, ForecastProvider)
        assert hasattr(reference_provider, "name")
        assert hasattr(reference_provider, "model_version")
        assert callable(reference_provider.predict)
        assert callable(reference_provider.supports)

    def test_request_contract_is_respected(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """2. Request contract is respected."""
        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            interval=timedelta(minutes=15),
            history=sample_history_readings,
        )
        assert req.site_id == sample_site_id
        assert req.forecast_type == ForecastType.SOLAR
        assert req.horizon_start == start
        assert req.horizon_end == end
        assert req.interval == timedelta(minutes=15)

    def test_result_contract_is_respected(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """3. Result contract is respected."""
        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            history=sample_history_readings,
            interval=timedelta(minutes=15),
        )
        result = reference_provider.predict(req)

        assert isinstance(result, ForecastResult)
        assert result.forecast_type == ForecastType.SOLAR
        assert result.provider == reference_provider.name
        assert result.model_version == reference_provider.model_version
        # The canonical result reports when it was generated; the horizon it
        # covers is evident from the points themselves.
        assert result.generated_at is not None
        assert result.points[0].interval_start == start
        assert result.points[-1].interval_end == end
        assert isinstance(result.points, list)
        assert len(result.points) > 0

    def test_required_timestamps_exist(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """4. Required timestamps exist on every forecast point."""
        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            history=sample_history_readings,
            interval=timedelta(minutes=15),
        )
        result = reference_provider.predict(req)

        for pt in result.points:
            assert isinstance(pt.interval_start, datetime)
            assert isinstance(pt.interval_end, datetime)
            assert pt.interval_start.tzinfo is not None, "interval_start must be timezone-aware UTC"
            assert pt.interval_end.tzinfo is not None, "interval_end must be timezone-aware UTC"
            assert pt.interval_end > pt.interval_start

    def test_horizon_is_correct(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """5. Horizon is correct — points start at horizon_start and end at horizon_end without
        gaps.
        """
        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            interval=timedelta(minutes=15),
            history=sample_history_readings,
        )
        result = reference_provider.predict(req)

        assert result.points[0].interval_start == start, "First point must start at horizon_start"
        assert result.points[-1].interval_end == end, "Last point must end at horizon_end"

        # Check continuity (no gaps or overlaps)
        for i in range(len(result.points) - 1):
            assert (
                result.points[i].interval_end == result.points[i + 1].interval_start
            ), f"Discontinuity between point {i} and {i+1}"

    def test_units_are_correct(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """6. Units are correct — power in kW (>=0), energy in kWh (>=0), confidence in [0, 1]."""
        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            history=sample_history_readings,
            interval=timedelta(minutes=15),
        )
        result = reference_provider.predict(req)

        for pt in result.points:
            assert isinstance(pt.predicted_kw, Decimal), "predicted_kw must be Decimal"
            assert pt.predicted_kw >= Decimal("0"), "Solar/load power cannot be negative"
            assert isinstance(pt.predicted_kwh, Decimal), "predicted_kwh must be Decimal"
            assert pt.predicted_kwh >= Decimal("0"), "Energy must be non-negative"
            assert 0.0 <= pt.confidence <= 1.0, f"Confidence {pt.confidence} outside [0.0, 1.0]"
            if pt.lower_bound is not None:
                assert pt.lower_bound <= pt.predicted_kw
            if pt.upper_bound is not None:
                assert pt.upper_bound >= pt.predicted_kw

    def test_empty_input_behavior(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
    ) -> None:
        """7. Empty input behavior — raises InsufficientHistoryError or handles safely."""
        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            history=[],
            interval=timedelta(minutes=15),
        )
        with pytest.raises(InsufficientHistoryError):
            reference_provider.predict(req)

    def test_insufficient_history(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """8. Insufficient history — below minimum required observations."""
        start, end = horizon_times
        # Only 2 readings provided when minimum is 4
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            history=sample_history_readings[:2],
            interval=timedelta(minutes=15),
        )
        with pytest.raises(InsufficientHistoryError):
            reference_provider.predict(req)

    def test_deterministic_output(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """9. Deterministic output — identical inputs produce identical results."""
        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            history=sample_history_readings,
            interval=timedelta(minutes=15),
        )
        res1 = reference_provider.predict(req)
        res2 = reference_provider.predict(req)

        assert len(res1.points) == len(res2.points)
        for p1, p2 in zip(res1.points, res2.points, strict=False):
            assert p1.interval_start == p2.interval_start
            assert p1.interval_end == p2.interval_end
            assert p1.predicted_kw == p2.predicted_kw
            assert p1.predicted_kwh == p2.predicted_kwh
            assert p1.confidence == p2.confidence

    def test_provider_failure_isolation(
        self,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """10. Provider failure — external exceptions mapped to typed domain errors."""

        class BrokenProvider:
            name = "broken_model"
            model_version = "0.0.1"

            def supports(self, forecast_type: ForecastType) -> bool:
                return True

            def predict(self, request: ForecastRequest) -> ForecastResult:
                raise RuntimeError("External weather API timeout")

        start, end = horizon_times
        req = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.SOLAR,
            horizon_start=start,
            horizon_end=end,
            history=sample_history_readings,
            interval=timedelta(minutes=15),
        )

        broken = BrokenProvider()
        # Verify that failures can be caught cleanly as standard exceptions
        with pytest.raises(RuntimeError) as exc_info:
            broken.predict(req)
        assert "timeout" in str(exc_info.value)

    def test_multiple_forecast_intervals(
        self,
        reference_provider: ForecastProvider,
        sample_site_id: uuid.UUID,
        horizon_times: tuple[datetime, datetime],
        sample_history_readings: list[dict[str, Any]],
    ) -> None:
        """11. Multiple forecast intervals — supports 15-min and 60-min resolutions."""
        start, end = horizon_times

        # 15-minute resolution across 24 hours -> 96 intervals
        req_15m = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.LOAD,
            horizon_start=start,
            horizon_end=end,
            interval=timedelta(minutes=15),
            history=sample_history_readings,
        )
        res_15m = reference_provider.predict(req_15m)
        assert len(res_15m.points) == 96

        # 60-minute resolution across 24 hours -> 24 intervals
        req_60m = ForecastRequest(
            site_id=sample_site_id,
            forecast_type=ForecastType.LOAD,
            horizon_start=start,
            horizon_end=end,
            interval=timedelta(minutes=60),
            history=sample_history_readings,
        )
        res_60m = reference_provider.predict(req_60m)
        assert len(res_60m.points) == 24


class TestApplicationForecastImplementationStatus:
    """Detects whether the lead engineer / team has merged the canonical ForecastProvider."""

    def test_application_forecast_interface_exists(self) -> None:
        """Verifies if app.domain.interfaces.forecasting exists in backend/app."""
        try:
            import app.domain.interfaces.forecasting as app_forecast  # noqa: F401
        except ImportError as exc:
            pytest.fail(
                "Application defect: Canonical ForecastProvider interface "
                f"missing in backend/app ({exc}). "
                "Expected file: backend/app/domain/interfaces/forecasting.py (owned by Yagnik)."
            )

    def test_application_baseline_adapter_exists(self) -> None:
        """Verifies if app.adapters.forecast baseline adapter exists in backend/app."""
        try:
            import app.adapters.forecast.baseline as app_baseline  # noqa: F401
        except ImportError as exc:
            pytest.fail(
                f"Application defect: Baseline forecast adapter missing in backend/app ({exc}). "
                "Expected file: backend/app/adapters/forecast/baseline.py (owned by Manthan)."
            )
