"""Fixtures for the forecast contract and integration tests.

Migrated onto the canonical contract in
`app.domain.interfaces.forecasting`. This module previously declared its own
`ForecastType`, `ForecastPoint`, `ForecastRequest`, `ForecastResult` and
`ForecastProvider`, which meant the contract tests verified those local copies
rather than anything the application actually uses. There is now exactly one
contract, repo-wide (docs/03_REPOSITORY_STRUCTURE.md: no duplicate domain
abstractions).

`ReferenceBaselineForecastProvider` is kept as a *second, independent*
implementation of that one contract — useful precisely because it is not the
shipped baseline: if both satisfy the service, the boundary is doing its job.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Meter, Site, User
from app.domain.enums import (
    ForecastType,
    MeterType,
    UserRole,
    UserStatus,
)
from app.domain.interfaces.forecasting import (
    ForecastPoint,
    ForecastProvider,
    ForecastRequest,
    ForecastResult,
    HistoricalObservation,
)
from app.main import create_app

# Re-exported for the test modules in this package: they import the contract
# from here, and these names must resolve to the canonical domain types rather
# than to local copies.
__all__ = [
    "ForecastPoint",
    "ForecastProvider",
    "ForecastRequest",
    "ForecastResult",
    "ForecastType",
    "HistoricalObservation",
    "InsufficientHistoryError",
    "ReferenceBaselineForecastProvider",
]

SITE_ID = uuid.UUID("40000000-0000-0000-0000-000000000001")
METER_ID = uuid.UUID("50000000-0000-0000-0000-000000000011")


class InsufficientHistoryError(ValueError):
    """Raised by the reference provider when it has too little history."""


class ReferenceBaselineForecastProvider:
    """A deterministic persistence-style baseline.

    Independent of the shipped `BaselineForecastProvider`: it averages the
    whole history rather than grouping by time of day. Satisfies the canonical
    `ForecastProvider` structurally, with no inheritance.
    """

    min_history_readings: int = 4

    def __init__(self, *, name: str = "baseline_persistence", version: str = "1.0.0") -> None:
        self._name = name
        self._version = version

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_version(self) -> str:
        return self._version

    def supports(self, forecast_type: ForecastType) -> bool:
        return forecast_type in (ForecastType.SOLAR, ForecastType.LOAD)

    def predict(self, request: ForecastRequest) -> ForecastResult:
        if not request.history:
            raise InsufficientHistoryError("No historical telemetry provided")
        if len(request.history) < self.min_history_readings:
            raise InsufficientHistoryError(
                f"Requires at least {self.min_history_readings} historical readings"
            )

        channel = "generation_kw" if request.forecast_type is ForecastType.SOLAR else "load_kw"
        values = [
            getattr(observation, channel)
            for observation in request.history
            if getattr(observation, channel) is not None
        ]
        average = (sum(values, Decimal("0")) / Decimal(len(values))) if values else Decimal("0")

        hours = Decimal(request.interval.total_seconds()) / Decimal(3600)
        points: list[ForecastPoint] = []
        current = request.horizon_start
        while current < request.horizon_end:
            following = min(current + request.interval, request.horizon_end)
            points.append(
                ForecastPoint(
                    interval_start=current,
                    interval_end=following,
                    predicted_kw=round(average, 3),
                    predicted_kwh=round(average * hours, 3),
                    confidence=Decimal("0.85"),
                    lower_bound=round(average * Decimal("0.8"), 3),
                    upper_bound=round(average * Decimal("1.2"), 3),
                )
            )
            current = following

        return ForecastResult(
            forecast_type=request.forecast_type,
            provider=self._name,
            model_version=self._version,
            generated_at=request.horizon_start,
            points=points,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_site_id() -> uuid.UUID:
    return SITE_ID


@pytest.fixture
def horizon_times() -> tuple[datetime, datetime]:
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    # 24 hours: the tests assert 96 quarter-hour and 24 hourly intervals.
    return start, start + timedelta(hours=24)


@pytest.fixture
def sample_history_readings() -> list[HistoricalObservation]:
    """A day of quarter-hourly history, in the canonical contract's shape."""
    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(days=1)
    return [
        HistoricalObservation(
            interval_start=base + timedelta(minutes=15 * i),
            interval_end=base + timedelta(minutes=15 * (i + 1)),
            generation_kw=Decimal("3.0"),
            load_kw=Decimal("1.5"),
        )
        for i in range(96)
    ]


@pytest.fixture
def reference_provider() -> ReferenceBaselineForecastProvider:
    return ReferenceBaselineForecastProvider()


@pytest.fixture
def seeded_site(db_session: Session) -> Site:
    """The site the API tests address.

    `forecast_points.site_id` is a foreign key, so this row has to exist or
    every request is correctly rejected as `SITE_NOT_FOUND`.
    """
    owner = User(
        display_name="Forecast Test Owner",
        role=UserRole.PROSUMER,
        status=UserStatus.ACTIVE,
        email=f"forecast-{uuid.uuid4().hex[:8]}@example.org",
    )
    db_session.add(owner)
    db_session.flush()

    site = Site(id=SITE_ID, owner_user_id=owner.id, name="Forecast Test Site")
    db_session.add(site)
    db_session.add(
        Meter(
            id=METER_ID,
            site_id=SITE_ID,
            meter_type=MeterType.SMART_METER,
            external_meter_ref=f"forecast-{METER_ID.hex[-8:]}",
        )
    )
    db_session.flush()
    return site


@pytest.fixture
def forecast_client(db_session: Session, seeded_site: Site) -> Iterator[TestClient]:
    """HTTP client bound to the test's rolled-back transaction.

    Keeps the suite repeatable and leaves nothing in the development database.
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
