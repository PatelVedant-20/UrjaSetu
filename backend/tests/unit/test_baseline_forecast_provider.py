"""Unit tests for `BaselineForecastProvider`.

Migrated onto the canonical contract in
`app.domain.interfaces.forecasting`. Every assertion from the original suite is
preserved; only the contract types changed, because the adapter no longer
defines its own.

Three things moved out of the provider by design and are asserted where they
now live:

* history filtering — the service passes only usable telemetry, so the provider
  simply skips channels it was not given;
* horizon validation — the service rejects a degenerate horizon before a
  provider is called;
* provider configuration (`reference_days`, `pv_capacity_kw`,
  `min_required_samples`) — constructor arguments, not request fields, so the
  request stays identical for every provider.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.adapters.forecast import BaselineForecastProvider
from app.domain.enums import ForecastType
from app.domain.interfaces.forecasting import (
    ForecastPoint,
    ForecastRequest,
    ForecastResult,
    HistoricalObservation,
)

SAMPLE_SITE_ID = UUID("20000000-0000-0000-0000-000000000001")
QUARTER = timedelta(minutes=15)


def _history(
    days: int = 7,
    base_date: datetime | None = None,
    gen_profile: dict[int, Decimal] | None = None,
    load_profile: dict[int, Decimal] | None = None,
) -> list[HistoricalObservation]:
    """A realistic diurnal history: solar around midday, load morning/evening."""
    if base_date is None:
        base_date = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)

    default_gen = {12: Decimal("4.0"), 13: Decimal("4.5"), 14: Decimal("4.0")}
    default_load = {8: Decimal("2.5"), 12: Decimal("1.5"), 19: Decimal("3.5")}
    gen_map = gen_profile or default_gen
    load_map = load_profile or default_load

    observations: list[HistoricalObservation] = []
    for day in range(days):
        day_start = base_date + timedelta(days=day)
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                start = day_start.replace(hour=hour, minute=minute)
                gen = gen_map.get(hour, Decimal("0.0"))
                load = (
                    gen_map.get(hour, Decimal("0.5"))
                    if load_profile is None
                    else load_map.get(hour, Decimal("0.5"))
                )
                observations.append(
                    HistoricalObservation(
                        interval_start=start,
                        interval_end=start + QUARTER,
                        generation_kw=gen,
                        load_kw=load,
                    )
                )
    return observations


def _request(**overrides: object) -> ForecastRequest:
    defaults: dict[str, object] = {
        "site_id": SAMPLE_SITE_ID,
        "forecast_type": ForecastType.SOLAR,
        "horizon_start": datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
        "horizon_end": datetime(2026, 9, 9, 0, 0, tzinfo=UTC),
        "interval": QUARTER,
        "history": _history(days=7),
    }
    return ForecastRequest(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_provider_satisfies_the_canonical_contract() -> None:
    provider = BaselineForecastProvider()

    assert provider.name == "baseline"
    assert provider.model_version == "1.0.0"
    assert provider.supports(ForecastType.SOLAR) is True
    assert provider.supports(ForecastType.LOAD) is True
    # Surplus is derived by the domain policy, not predicted by this provider.
    assert provider.supports(ForecastType.SURPLUS) is False


def test_valid_solar_prediction() -> None:
    provider = BaselineForecastProvider(reference_days=7, pv_capacity_kw=Decimal("5.0"))

    result = provider.predict(_request())

    assert isinstance(result, ForecastResult)
    assert result.forecast_type is ForecastType.SOLAR
    assert result.provider == "baseline"
    assert len(result.points) == 96  # 24 hours * 4
    assert sum((p.predicted_kwh or Decimal("0")) for p in result.points) > Decimal("0")

    midday = [p for p in result.points if p.interval_start.hour == 12]
    assert midday
    for point in midday:
        assert point.predicted_kw == Decimal("4.000")
        assert point.predicted_kwh == Decimal("1.000")  # 4 kW * 0.25 h
        assert point.confidence is not None
        assert point.confidence > Decimal("0.8")
        assert point.lower_bound is not None
        assert point.upper_bound is not None

    night = [p for p in result.points if p.interval_start.hour in (1, 2, 3)]
    assert all(p.predicted_kw == Decimal("0.000") for p in night)


def test_load_prediction() -> None:
    provider = BaselineForecastProvider()

    result = provider.predict(
        _request(
            forecast_type=ForecastType.LOAD,
            horizon_start=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
            horizon_end=datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
        )
    )

    assert len(result.points) == 4
    assert all((p.predicted_kw or Decimal("0")) > Decimal("0") for p in result.points)


def test_output_is_deterministic() -> None:
    """Same request, same result — required by docs/10_TESTING_AND_INTEGRATION.md."""
    provider = BaselineForecastProvider()
    request = _request()

    first = provider.predict(request)
    second = provider.predict(request)

    assert [(p.interval_start, p.predicted_kw, p.confidence) for p in first.points] == [
        (p.interval_start, p.predicted_kw, p.confidence) for p in second.points
    ]


def test_constant_history_yields_that_constant_with_no_spread() -> None:
    base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    history = [
        HistoricalObservation(
            interval_start=base + timedelta(days=d),
            interval_end=base + timedelta(days=d) + QUARTER,
            generation_kw=Decimal("3.0"),
            load_kw=Decimal("1.0"),
        )
        for d in range(5)
    ]

    result = BaselineForecastProvider().predict(
        _request(
            horizon_start=base + timedelta(days=5),
            horizon_end=base + timedelta(days=5) + QUARTER,
            history=history,
        )
    )

    point = result.points[0]
    assert point.predicted_kw == Decimal("3.000")
    # No variation means the bounds collapse onto the prediction.
    assert point.lower_bound == Decimal("3.000")
    assert point.upper_bound == Decimal("3.000")


def test_insufficient_history_is_refused_when_a_minimum_is_configured() -> None:
    provider = BaselineForecastProvider(min_required_samples=1)

    with pytest.raises(ValueError, match="usable measurements"):
        provider.predict(_request(history=[]))


def test_unmeasured_channels_contribute_nothing() -> None:
    """A channel the meter did not measure must not be read as zero.

    The service already filters out unusable telemetry; what reaches a provider
    can still have individual channels missing.
    """
    base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    history = [
        HistoricalObservation(
            interval_start=base + timedelta(days=d),
            interval_end=base + timedelta(days=d) + QUARTER,
            generation_kw=None,
            load_kw=Decimal("2.0"),
        )
        for d in range(3)
    ]
    provider = BaselineForecastProvider(min_required_samples=1)

    with pytest.raises(ValueError, match="usable measurements"):
        provider.predict(
            _request(
                forecast_type=ForecastType.SOLAR,
                horizon_start=base + timedelta(days=3),
                horizon_end=base + timedelta(days=3) + QUARTER,
                history=history,
            )
        )


def test_no_history_for_a_time_of_day_predicts_zero_with_no_confidence() -> None:
    """ "No expectation" is reported honestly rather than guessed."""
    base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    history = [
        HistoricalObservation(
            interval_start=base,
            interval_end=base + QUARTER,
            generation_kw=Decimal("3.0"),
        )
    ]

    result = BaselineForecastProvider().predict(
        _request(
            horizon_start=base + timedelta(days=1, hours=5),
            horizon_end=base + timedelta(days=1, hours=5) + QUARTER,
            history=history,
        )
    )

    point = result.points[0]
    assert point.predicted_kw == Decimal("0")
    assert point.confidence == Decimal("0")


def test_degenerate_horizon_produces_no_points() -> None:
    """The service rejects such a horizon before a provider is reached.

    Asserted here so the provider is known not to loop or invent points if one
    ever slips through.
    """
    moment = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)

    result = BaselineForecastProvider().predict(_request(horizon_start=moment, horizon_end=moment))

    assert result.points == []


def test_pv_capacity_caps_prediction_and_upper_bound() -> None:
    """A site cannot generate more than its inverter is rated for."""
    provider = BaselineForecastProvider(pv_capacity_kw=Decimal("5.0"))
    history = _history(days=7, gen_profile={12: Decimal("9.0")})

    result = provider.predict(
        _request(
            horizon_start=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
            horizon_end=datetime(2026, 9, 8, 13, 0, tzinfo=UTC),
            history=history,
        )
    )

    for point in result.points:
        assert point.predicted_kw == Decimal("5.000")
        assert point.upper_bound is not None
        assert point.upper_bound <= Decimal("5.0")


def test_points_are_contiguous_and_cover_the_horizon() -> None:
    result = BaselineForecastProvider().predict(
        _request(
            horizon_start=datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
            horizon_end=datetime(2026, 9, 8, 1, 0, tzinfo=UTC),
        )
    )

    assert [p.interval_start for p in result.points] == [
        datetime(2026, 9, 8, 0, m, tzinfo=UTC) for m in (0, 15, 30, 45)
    ]
    for point in result.points:
        assert isinstance(point, ForecastPoint)
        assert point.interval_end - point.interval_start == QUARTER


def test_confidence_stays_within_zero_and_one() -> None:
    """The service rejects anything outside [0, 1]; the provider must not emit it."""
    result = BaselineForecastProvider().predict(_request())

    for point in result.points:
        assert point.confidence is not None
        assert Decimal("0") <= point.confidence <= Decimal("1")


def test_bounds_are_ordered() -> None:
    result = BaselineForecastProvider().predict(_request())

    for point in result.points:
        assert point.lower_bound is not None
        assert point.upper_bound is not None
        assert point.lower_bound <= point.upper_bound


def test_naive_timestamps_are_normalised_to_utc() -> None:
    """docs/00_PROJECT_BIBLE.md section 6: UTC everywhere in storage."""
    result = BaselineForecastProvider().predict(
        _request(
            horizon_start=datetime(2026, 9, 8, 0, 0),
            horizon_end=datetime(2026, 9, 8, 1, 0),
        )
    )

    assert all(p.interval_start.tzinfo is not None for p in result.points)
