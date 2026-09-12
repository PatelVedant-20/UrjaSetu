"""Shared fixtures and payload generators for Telemetry API tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def telemetry_client() -> Iterator[TestClient]:
    """TestClient for Telemetry API endpoints."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sample_site_id() -> str:
    """Deterministic UUID for a test site."""
    return "40000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_meter_id() -> str:
    """Deterministic UUID for a test meter."""
    return "50000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_asset_id() -> str:
    """Deterministic UUID for a test solar asset."""
    return "60000000-0000-0000-0000-000000000001"


@pytest.fixture
def make_reading_payload(
    sample_site_id: str, sample_meter_id: str, sample_asset_id: str
) -> Callable[..., dict[str, Any]]:
    """Factory generating normalized telemetry reading payloads per docs/04_DATA_MODEL.md."""

    def _make(**overrides: Any) -> dict[str, Any]:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - timedelta(minutes=15)
        defaults: dict[str, Any] = {
            "meter_id": sample_meter_id,
            "site_id": sample_site_id,
            "energy_asset_id": sample_asset_id,
            "timestamp": now.isoformat(),
            "interval_start": start.isoformat(),
            "interval_end": now.isoformat(),
            "generation_kw": 4.5,
            "load_kw": 1.5,
            "grid_import_kw": 0.0,
            "grid_export_kw": 3.0,
            "energy_kwh": 1.125,
            "battery_soc": 85.0,
            "source": "smart_meter",
        }
        defaults.update(overrides)
        return defaults

    return _make


@pytest.fixture
def make_batch_payloads(
    make_reading_payload: Callable[..., dict[str, Any]]
) -> Callable[[int], list[dict[str, Any]]]:
    """Factory generating a sequence of consecutive 15-minute interval readings."""

    def _make(count: int = 4) -> list[dict[str, Any]]:
        base_time = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        batch = []
        for i in range(count):
            t = base_time + timedelta(minutes=15 * i)
            t_start = t - timedelta(minutes=15)
            batch.append(
                make_reading_payload(
                    timestamp=t.isoformat(),
                    interval_start=t_start.isoformat(),
                    interval_end=t.isoformat(),
                    generation_kw=round(4.0 + (i * 0.5), 2),
                    load_kw=round(1.2 + (i * 0.1), 2),
                    grid_export_kw=round(2.8 + (i * 0.4), 2),
                )
            )
        return batch

    return _make
