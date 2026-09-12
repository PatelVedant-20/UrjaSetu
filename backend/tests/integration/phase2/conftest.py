"""Phase 2 fixtures — a meter to hang telemetry from, and reading builders.

Reuses the Phase 1 registry factories rather than re-creating them: telemetry
belongs to a meter, which belongs to a site, which belongs to a user.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from app.domain.enums import TelemetrySource
from app.domain.interfaces.telemetry import NormalizedReading

# Re-exported so Phase 2 tests can build the registry a reading hangs off
# (user -> site -> meter -> asset) without duplicating those factories.
# Imported rather than declared via `pytest_plugins`, which pytest only permits
# in the rootdir conftest — and imported rather than moved, because
# phase1/conftest.py belongs to Phase 1 and is not this phase's to reorganise.
from tests.integration.phase1.conftest import (  # noqa: F401
    make_energy_asset,
    make_inverter,
    make_meter,
    make_site,
    make_user,
)

# Fixed instant so every quality assertion is reproducible.
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=15)


@pytest.fixture
def make_reading() -> Callable[..., NormalizedReading]:
    """Build a normalized reading. Defaults are valid and current at `NOW`."""

    def _make(meter_id: UUID, **overrides: Any) -> NormalizedReading:
        interval_start = overrides.pop("interval_start", NOW - INTERVAL)
        defaults: dict[str, Any] = {
            "meter_id": meter_id,
            "timestamp": interval_start + INTERVAL,
            "interval_start": interval_start,
            "interval_end": interval_start + INTERVAL,
            "source": TelemetrySource.SIMULATOR,
            "generation_kw": Decimal("3.5000"),
            "load_kw": Decimal("1.2000"),
            "grid_import_kw": Decimal("0.0000"),
            "grid_export_kw": Decimal("2.3000"),
            "energy_kwh": Decimal("0.8750"),
        }
        return NormalizedReading(**{**defaults, **overrides})

    return _make
