"""Unit tests for SamePeriodAverageForecastProvider."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.adapters.forecast import (
    ForecastPoint,
    ForecastProvider,
    ForecastRequest,
    ForecastResult,
    InsufficientHistoryError,
    InvalidHorizonError,
    SamePeriodAverageForecastProvider,
)
from app.domain.enums import TelemetrySource
from app.domain.interfaces.telemetry import NormalizedReading

SAMPLE_SITE_ID = UUID("20000000-0000-0000-0000-000000000001")
SAMPLE_METER_ID = UUID("10000000-0000-0000-0000-000000000001")


def _make_historical_readings(
    days: int = 7,
    base_date: datetime | None = None,
    gen_profile: dict[int, Decimal] | None = None,
    load_profile: dict[int, Decimal] | None = None,
) -> list[NormalizedReading]:
    """Helper to generate a realistic sequence of historical NormalizedReadings."""
    if base_date is None:
        base_date = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)

    readings: list[NormalizedReading] = []
    default_gen = {12: Decimal("4.0"), 13: Decimal("4.5"), 14: Decimal("4.0")}
    default_load = {8: Decimal("2.5"), 12: Decimal("1.5"), 19: Decimal("3.5")}

    gen_map = gen_profile or default_gen
    load_map = load_profile or default_load

    for day in range(days):
        day_start = base_date + timedelta(days=day)
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                start = day_start.replace(hour=hour, minute=minute)
                end = start + timedelta(minutes=15)

                gen = gen_map.get(hour, Decimal("0.0"))
                if load_profile is None:
                    load = gen_map.get(hour, Decimal("0.5"))
                else:
                    load = load_map.get(hour, Decimal("0.5"))

                r = NormalizedReading(
                    meter_id=SAMPLE_METER_ID,
                    timestamp=start,
                    interval_start=start,
                    interval_end=end,
                    source=TelemetrySource.METER,
                    generation_kw=gen,
                    load_kw=load,
                )
                readings.append(r)
    return readings


def test_provider_protocol_conformance() -> None:
    provider = SamePeriodAverageForecastProvider()
    assert isinstance(provider, ForecastProvider)
    assert provider.provider_id == "baseline_same_period_average"
    assert provider.model_version == "0.1.0"


def test_valid_solar_prediction() -> None:
    provider = SamePeriodAverageForecastProvider(reference_days=7)
    history = _make_historical_readings(days=7)

    horizon_start = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)
    horizon_end = datetime(2026, 9, 9, 0, 0, tzinfo=UTC)

    request = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="solar",
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        history=history,
        interval_minutes=15,
        pv_capacity_kw=Decimal("5.0"),
    )

    result = provider.generate_forecast(request)

    assert isinstance(result, ForecastResult)
    assert result.site_id == SAMPLE_SITE_ID
    assert result.forecast_type == "solar"
    assert len(result.points) == 96  # 24 hours * 4
    assert result.total_predicted_kwh > Decimal("0.0")

    # Check midday solar predictions vs nighttime
    midday_points = [p for p in result.points if p.interval_start.hour == 12]
    for p in midday_points:
        assert p.predicted_kw == Decimal("4.000")
        assert p.predicted_kwh == Decimal("1.000")  # 4 kW * 0.25h
        assert p.confidence > Decimal("0.8")
        assert p.lower_bound is not None
        assert p.upper_bound is not None

    night_points = [p for p in result.points if p.interval_start.hour in (1, 2, 3)]
    for p in night_points:
        assert p.predicted_kw == Decimal("0.000")


def test_valid_load_and_surplus_prediction() -> None:
    provider = SamePeriodAverageForecastProvider()
    history = _make_historical_readings(days=7)

    horizon_start = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    horizon_end = datetime(2026, 9, 8, 13, 0, tzinfo=UTC)

    # 1. Load forecast
    load_req = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="load",
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        history=history,
    )
    load_res = provider.generate_forecast(load_req)
    assert len(load_res.points) == 4
    for p in load_res.points:
        assert p.predicted_kw > Decimal("0.0")

    # 2. Surplus forecast (generation - load)
    surplus_req = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="surplus",
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        history=history,
    )
    surplus_res = provider.generate_forecast(surplus_req)
    assert len(surplus_res.points) == 4


def test_deterministic_output() -> None:
    provider = SamePeriodAverageForecastProvider()
    history = _make_historical_readings(days=7)

    horizon_start = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)
    horizon_end = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)

    request = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="solar",
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        history=history,
    )

    result1 = provider.generate_forecast(request)
    result2 = provider.generate_forecast(request)

    assert len(result1.points) == len(result2.points)
    for p1, p2 in zip(result1.points, result2.points, strict=True):
        assert p1.interval_start == p2.interval_start
        assert p1.interval_end == p2.interval_end
        assert p1.predicted_kw == p2.predicted_kw
        assert p1.predicted_kwh == p2.predicted_kwh
        assert p1.confidence == p2.confidence
        assert p1.lower_bound == p2.lower_bound
        assert p1.upper_bound == p2.upper_bound


def test_constant_flat_data() -> None:
    provider = SamePeriodAverageForecastProvider()
    constant_val = Decimal("3.25")

    # Generate 5 days of constant 3.25 kW readings
    history = [
        NormalizedReading(
            meter_id=SAMPLE_METER_ID,
            timestamp=datetime(2026, 9, 1, 0, 0, tzinfo=UTC) + timedelta(minutes=15 * i),
            interval_start=datetime(2026, 9, 1, 0, 0, tzinfo=UTC) + timedelta(minutes=15 * i),
            interval_end=datetime(2026, 9, 1, 0, 15, tzinfo=UTC) + timedelta(minutes=15 * i),
            source=TelemetrySource.METER,
            generation_kw=constant_val,
        )
        for i in range(5 * 96)
    ]

    request = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="solar",
        horizon_start=datetime(2026, 9, 10, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 9, 10, 4, 0, tzinfo=UTC),
        history=history,
    )

    result = provider.generate_forecast(request)
    for p in result.points:
        assert p.predicted_kw == Decimal("3.250")
        assert p.lower_bound == Decimal("3.250")  # zero variance
        assert p.upper_bound == Decimal("3.250")  # zero variance


def test_empty_history_insufficient_error() -> None:
    provider = SamePeriodAverageForecastProvider()
    request = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="solar",
        horizon_start=datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 9, 8, 1, 0, tzinfo=UTC),
        history=[],
        min_required_samples=1,
    )

    with pytest.raises(InsufficientHistoryError, match="History contains 0 valid measurements"):
        provider.generate_forecast(request)


def test_unavailable_sources_filtered_out() -> None:
    provider = SamePeriodAverageForecastProvider()
    # History with only unavailable/empty readings
    history = [
        NormalizedReading(
            meter_id=SAMPLE_METER_ID,
            timestamp=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
            interval_start=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
            interval_end=datetime(2026, 9, 1, 10, 15, tzinfo=UTC),
            source=TelemetrySource.METER,
            source_unavailable=True,
        )
    ]

    request = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="solar",
        horizon_start=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 9, 8, 11, 0, tzinfo=UTC),
        history=history,
        min_required_samples=1,
    )

    with pytest.raises(InsufficientHistoryError):
        provider.generate_forecast(request)


def test_invalid_horizon_dates() -> None:
    with pytest.raises(InvalidHorizonError, match="horizon_end .* must be after horizon_start"):
        ForecastRequest(
            site_id=SAMPLE_SITE_ID,
            forecast_type="solar",
            horizon_start=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
            horizon_end=datetime(2026, 9, 8, 10, 0, tzinfo=UTC),  # End before start
            history=[],
        )


def test_pv_capacity_capping() -> None:
    provider = SamePeriodAverageForecastProvider()
    # History with high solar readings
    history = _make_historical_readings(
        days=3,
        gen_profile={12: Decimal("8.0")},
    )

    request = ForecastRequest(
        site_id=SAMPLE_SITE_ID,
        forecast_type="solar",
        horizon_start=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
        horizon_end=datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
        history=history,
        pv_capacity_kw=Decimal("5.0"),  # Cap at 5.0 kW
    )

    result = provider.generate_forecast(request)
    for p in result.points:
        assert p.predicted_kw <= Decimal("5.000")
        assert p.upper_bound is not None and p.upper_bound <= Decimal("5.000")


def test_forecast_point_validation() -> None:
    # Invalid confidence > 1.0
    with pytest.raises(ValueError, match="confidence must be in"):
        ForecastPoint(
            interval_start=datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
            interval_end=datetime(2026, 9, 8, 0, 15, tzinfo=UTC),
            predicted_kw=Decimal("1.0"),
            predicted_kwh=Decimal("0.25"),
            confidence=Decimal("1.5"),
        )

    # Invalid negative predicted_kw
    with pytest.raises(ValueError, match="predicted_kw cannot be negative"):
        ForecastPoint(
            interval_start=datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
            interval_end=datetime(2026, 9, 8, 0, 15, tzinfo=UTC),
            predicted_kw=Decimal("-1.0"),
            predicted_kwh=Decimal("0.25"),
            confidence=Decimal("0.8"),
        )
