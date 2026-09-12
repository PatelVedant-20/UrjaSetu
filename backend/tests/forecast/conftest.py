"""Shared fixtures, canonical contracts, and test utilities for Forecast tests.

Implements the contract definitions specified by:
  - docs/01_FINAL_ARCHITECTURE.md (Forecasting Engine)
  - docs/04_DATA_MODEL.md (Entities 11 & 12: forecast_runs, forecast_points)
  - docs/05_API_SPEC.md (Forecast endpoints & surplus)
  - docs/07_CODING_PHASES.md (Phase 3 ForecastProvider protocol)
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


# ---------------------------------------------------------------------------
# Canonical Domain Contracts
# ---------------------------------------------------------------------------


class ForecastType(str, enum.Enum):
    """Types of forecast supported per docs/04_DATA_MODEL.md entity 11."""

    SOLAR = "solar"
    LOAD = "load"
    SURPLUS = "surplus"


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """One forecast interval bucket per docs/04_DATA_MODEL.md entity 12."""

    interval_start: datetime
    interval_end: datetime
    predicted_kw: Decimal
    predicted_kwh: Decimal
    confidence: float
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None

    def __post_init__(self) -> None:
        if self.interval_start.tzinfo is None or self.interval_end.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware UTC")
        if self.interval_end <= self.interval_start:
            raise ValueError("interval_end must be after interval_start")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.predicted_kw < Decimal("0"):
            raise ValueError(f"predicted_kw must be >= 0, got {self.predicted_kw}")


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    """The request contract provided to a ForecastProvider."""

    site_id: uuid.UUID
    forecast_type: ForecastType
    horizon_start: datetime
    horizon_end: datetime
    resolution_minutes: int = 15
    historical_readings: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.horizon_start.tzinfo is None or self.horizon_end.tzinfo is None:
            raise ValueError("Horizon timestamps must be timezone-aware UTC")
        if self.horizon_end <= self.horizon_start:
            raise ValueError("horizon_end must be strictly greater than horizon_start")
        if self.resolution_minutes <= 0:
            raise ValueError("resolution_minutes must be positive")


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """The result contract returned by a ForecastProvider."""

    forecast_type: ForecastType
    provider_name: str
    model_version: str
    horizon_start: datetime
    horizon_end: datetime
    points: list[ForecastPoint]


class ForecastError(Exception):
    """Base domain error for forecasting failures."""


class InsufficientHistoryError(ForecastError):
    """Raised when available historical readings are below provider requirements."""


class ForecastProviderError(ForecastError):
    """Raised when an external or underlying forecast model fails."""


@runtime_checkable
class ForecastProvider(Protocol):
    """Canonical ForecastProvider interface per docs/07_CODING_PHASES.md."""

    name: str
    version: str

    def generate_forecast(self, request: ForecastRequest) -> ForecastResult:
        """Generate time-series forecast points for the requested horizon."""
        ...


# ---------------------------------------------------------------------------
# Conforming Reference Provider (for testing contract harness)
# ---------------------------------------------------------------------------


class ReferenceBaselineForecastProvider:
    """A deterministic baseline provider satisfying ForecastProvider protocol."""

    name: str = "baseline_persistence"
    version: str = "1.0.0"
    min_history_readings: int = 4

    def generate_forecast(self, request: ForecastRequest) -> ForecastResult:
        if not request.historical_readings:
            raise InsufficientHistoryError("No historical telemetry provided")
        if len(request.historical_readings) < self.min_history_readings:
            raise InsufficientHistoryError(
                f"Requires at least {self.min_history_readings} historical readings"
            )

        # Baseline: compute average of historical generation/load
        total_kw = Decimal("0")
        count = 0
        for r in request.historical_readings:
            kw = r.get("generation_kw" if request.forecast_type == ForecastType.SOLAR else "load_kw")
            if kw is not None:
                total_kw += Decimal(str(kw))
                count += 1
        avg_kw = (total_kw / Decimal(count)) if count > 0 else Decimal("0")

        points: list[ForecastPoint] = []
        cur = request.horizon_start
        step = timedelta(minutes=request.resolution_minutes)
        hours = Decimal(str(request.resolution_minutes)) / Decimal("60")

        while cur < request.horizon_end:
            nxt = min(cur + step, request.horizon_end)
            kwh = avg_kw * hours
            points.append(
                ForecastPoint(
                    interval_start=cur,
                    interval_end=nxt,
                    predicted_kw=round(avg_kw, 3),
                    predicted_kwh=round(kwh, 3),
                    confidence=0.85,
                    lower_bound=round(avg_kw * Decimal("0.8"), 3),
                    upper_bound=round(avg_kw * Decimal("1.2"), 3),
                )
            )
            cur = nxt

        return ForecastResult(
            forecast_type=request.forecast_type,
            provider_name=self.name,
            model_version=self.version,
            horizon_start=request.horizon_start,
            horizon_end=request.horizon_end,
            points=points,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_site_id() -> uuid.UUID:
    return uuid.UUID("40000000-0000-0000-0000-000000000001")


@pytest.fixture
def horizon_times() -> tuple[datetime, datetime]:
    start = datetime(2026, 3, 16, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 3, 17, 0, 0, 0, tzinfo=timezone.utc)
    return start, end


@pytest.fixture
def sample_history_readings(sample_site_id: uuid.UUID) -> list[dict[str, Any]]:
    """Generate 24 hours of 15m historical telemetry readings (96 readings)."""
    base = datetime(2026, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
    readings = []
    for i in range(96):
        t = base + timedelta(minutes=15 * i)
        # Solar curve: bell curve roughly between 6 AM and 6 PM
        hour = t.hour + (t.minute / 60.0)
        solar = 5.0 * max(0.0, 1.0 - ((hour - 12.0) / 4.0) ** 2) if 6 <= hour <= 18 else 0.0
        load = 1.5 + (0.8 if 18 <= hour <= 22 else 0.2)
        readings.append(
            {
                "site_id": str(sample_site_id),
                "timestamp": t.isoformat(),
                "interval_start": t.isoformat(),
                "interval_end": (t + timedelta(minutes=15)).isoformat(),
                "generation_kw": round(solar, 3),
                "load_kw": round(load, 3),
                "quality_status": "valid",
            }
        )
    return readings


@pytest.fixture
def reference_provider() -> ForecastProvider:
    return ReferenceBaselineForecastProvider()


@pytest.fixture
def forecast_client() -> TestClient:
    """FastAPI TestClient for forecast API testing."""
    app = create_app()
    with TestClient(app) as client:
        yield client
