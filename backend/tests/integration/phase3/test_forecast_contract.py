"""Phase 3: the provider contract itself.

Proves the boundary is structural — an implementation only has to match the
shape, with no import of, or inheritance from, UrjaSetu base classes. That is
what lets a future OpenSTEF, XGBoost or hosted-model provider be plugged in
without changing the forecasting service (docs/06_OPEN_SOURCE_INTEGRATION.md
section 5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.domain.enums import ForecastType
from app.domain.interfaces.forecasting import (
    ForecastPoint,
    ForecastProvider,
    ForecastRequest,
    ForecastResult,
    HistoricalObservation,
)

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
IV = timedelta(minutes=15)


class ThirdPartyProvider:
    """A provider written with no knowledge of UrjaSetu's internals.

    Imports only the contract; inherits nothing.
    """

    name = "third-party"
    model_version = "0.1"

    def supports(self, forecast_type: ForecastType) -> bool:
        return forecast_type is ForecastType.SOLAR

    def predict(self, request: ForecastRequest) -> ForecastResult:
        return ForecastResult(
            forecast_type=request.forecast_type,
            provider=self.name,
            model_version=self.model_version,
            generated_at=T0,
            points=[
                ForecastPoint(
                    interval_start=request.horizon_start,
                    interval_end=request.horizon_start + request.interval,
                    predicted_kw=Decimal("1"),
                )
            ],
        )


def _request(**overrides: object) -> ForecastRequest:
    defaults: dict[str, object] = {
        "site_id": uuid4(),
        "forecast_type": ForecastType.SOLAR,
        "horizon_start": T0,
        "horizon_end": T0 + timedelta(hours=1),
        "interval": IV,
    }
    return ForecastRequest(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_an_unrelated_class_satisfies_the_provider_type() -> None:
    provider: ForecastProvider = ThirdPartyProvider()

    assert provider.name == "third-party"
    assert provider.supports(ForecastType.SOLAR) is True
    assert provider.supports(ForecastType.LOAD) is False


def test_provider_returns_the_contract_types() -> None:
    result = ThirdPartyProvider().predict(_request())

    assert isinstance(result, ForecastResult)
    assert all(isinstance(p, ForecastPoint) for p in result.points)


def test_expected_point_count_divides_the_horizon() -> None:
    assert _request().expected_point_count == 4
    assert _request(interval=timedelta(minutes=30)).expected_point_count == 2
    assert _request(horizon_end=T0 + timedelta(days=1)).expected_point_count == 96


def test_expected_point_count_is_zero_for_a_degenerate_horizon() -> None:
    """A caller must not divide by a zero interval or an inverted horizon."""
    assert _request(interval=timedelta(0)).expected_point_count == 0
    assert _request(horizon_end=T0 - timedelta(hours=1)).expected_point_count == 0


def test_request_history_defaults_to_empty() -> None:
    """A cold-start site still reaches the provider; it decides what to do."""
    assert _request().history == ()


def test_history_preserves_unmeasured_channels() -> None:
    """`None` means not measured — never silently zero."""
    observation = HistoricalObservation(interval_start=T0, interval_end=T0 + IV)

    assert observation.generation_kw is None
    assert observation.load_kw is None


def test_contract_objects_are_immutable() -> None:
    """An observation and a prediction are facts; nothing downstream edits them."""
    point = ForecastPoint(interval_start=T0, interval_end=T0 + IV)

    for obj, attr, value in (
        (point, "predicted_kw", Decimal("9")),
        (_request(), "site_id", uuid4()),
        (HistoricalObservation(interval_start=T0, interval_end=T0 + IV), "load_kw", Decimal("1")),
    ):
        try:
            setattr(obj, attr, value)
        except Exception as exc:
            assert exc.__class__.__name__ == "FrozenInstanceError"
        else:  # pragma: no cover - a mutable contract object is a defect
            raise AssertionError(f"{type(obj).__name__}.{attr} should be immutable")


def test_optional_uncertainty_is_genuinely_optional() -> None:
    """A non-probabilistic provider reports no confidence rather than a fake one."""
    point = ForecastPoint(interval_start=T0, interval_end=T0 + IV, predicted_kw=Decimal("3"))

    assert point.confidence is None
    assert point.lower_bound is None
    assert point.upper_bound is None


def test_generated_at_is_separate_from_the_predicted_intervals() -> None:
    result = ThirdPartyProvider().predict(_request())

    assert result.generated_at == T0
    assert result.points[0].interval_start == T0
    # Same value here only because the stub pins both; they are different fields
    # with different meanings, and the service stores them separately.
    assert result.generated_at is not result.points[0].interval_end
