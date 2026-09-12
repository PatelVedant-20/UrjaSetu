"""Phase 3 fixtures.

Providers here are **stand-ins for the contract, not forecasting algorithms**.
Manthan's baseline provider lives in `app/adapters/forecast/` and is tested in
his own directory; these exist only to prove the orchestration layer can drive
anything that satisfies `ForecastProvider`, including one that misbehaves.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.enums import ForecastType
from app.domain.interfaces.forecasting import (
    ForecastPoint,
    ForecastRequest,
    ForecastResult,
)

# Re-exported so Phase 3 tests can build the registry a forecast hangs off
# (user -> site -> meter) without duplicating those factories.
from tests.integration.phase1.conftest import (  # noqa: F401
    make_energy_asset,
    make_meter,
    make_site,
    make_user,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=15)


class StubProvider:
    """A deterministic provider that emits a constant power value.

    Satisfies `ForecastProvider` structurally — no inheritance — which is the
    point: an adapter only has to match the shape.
    """

    def __init__(
        self,
        *,
        name: str = "stub",
        model_version: str = "1.0.0",
        value: Decimal = Decimal("4.0"),
        supported: Sequence[ForecastType] | None = None,
    ) -> None:
        self._name = name
        self._model_version = model_version
        self._value = value
        self._supported = tuple(
            supported if supported is not None else (ForecastType.SOLAR, ForecastType.LOAD)
        )
        self.calls: list[ForecastRequest] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return self._model_version

    def supports(self, forecast_type: ForecastType) -> bool:
        return forecast_type in self._supported

    def predict(self, request: ForecastRequest) -> ForecastResult:
        self.calls.append(request)
        points = [
            ForecastPoint(
                interval_start=request.horizon_start + request.interval * i,
                interval_end=request.horizon_start + request.interval * (i + 1),
                predicted_kw=self._value,
                predicted_kwh=self._value
                * Decimal(request.interval.total_seconds())
                / Decimal(3600),
                confidence=Decimal("0.8"),
            )
            for i in range(request.expected_point_count)
        ]
        return ForecastResult(
            forecast_type=request.forecast_type,
            provider=self._name,
            model_version=self._model_version,
            generated_at=NOW,
            points=points,
        )


class FailingProvider(StubProvider):
    """A provider that raises, to prove failures stay observable."""

    def predict(self, request: ForecastRequest) -> ForecastResult:
        raise RuntimeError("model artefact unavailable")


class MisbehavingProvider(StubProvider):
    """A provider that satisfies the type but violates the contract."""

    def __init__(self, *, mode: str, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.mode = mode

    def predict(self, request: ForecastRequest) -> ForecastResult:
        base = super().predict(request)
        points = list(base.points)

        if self.mode == "empty":
            points = []
        elif self.mode == "outside_horizon":
            points = [
                ForecastPoint(
                    interval_start=request.horizon_end + request.interval,
                    interval_end=request.horizon_end + request.interval * 2,
                    predicted_kw=Decimal("1"),
                )
            ]
        elif self.mode == "duplicate_interval":
            points = [points[0], points[0]]
        elif self.mode == "inverted_interval":
            points = [
                ForecastPoint(
                    interval_start=request.horizon_start + request.interval,
                    interval_end=request.horizon_start,
                    predicted_kw=Decimal("1"),
                )
            ]
        elif self.mode == "bad_confidence":
            points = [
                ForecastPoint(
                    interval_start=request.horizon_start,
                    interval_end=request.horizon_start + request.interval,
                    predicted_kw=Decimal("1"),
                    confidence=Decimal("5"),
                )
            ]
        elif self.mode == "wrong_type":
            other = (
                ForecastType.LOAD
                if request.forecast_type is ForecastType.SOLAR
                else ForecastType.SOLAR
            )
            return ForecastResult(
                forecast_type=other,
                provider=self.name,
                model_version=self.model_version,
                generated_at=NOW,
                points=points,
            )

        return ForecastResult(
            forecast_type=request.forecast_type,
            provider=self.name,
            model_version=self.model_version,
            generated_at=NOW,
            points=points,
        )


@pytest.fixture
def make_provider() -> Callable[..., StubProvider]:
    def _make(**kwargs: object) -> StubProvider:
        return StubProvider(**kwargs)  # type: ignore[arg-type]

    return _make
