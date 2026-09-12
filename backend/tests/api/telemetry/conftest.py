"""Shared fixtures and payload generators for Telemetry API tests.

Two pieces of test infrastructure were missing and are supplied here:

* **A seeded registry.** The payloads reference deterministic site, meter and
  asset UUIDs. `telemetry_readings.meter_id` is a foreign key, so those rows
  have to exist or every ingest is correctly rejected as `METER_NOT_FOUND`.
* **Transaction isolation.** The client runs inside a transaction that is
  rolled back after each test, so runs are repeatable and nothing leaks into
  the development database.

Assertions are untouched.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import EnergyAsset, Meter, Site, User
from app.domain.enums import (
    EnergyAssetStatus,
    EnergyAssetType,
    MeterType,
    UserRole,
    UserStatus,
)
from app.main import create_app

# Deterministic identifiers the payload factories below refer to.
SITE_A = uuid.UUID("40000000-0000-0000-0000-000000000001")
SITE_B = uuid.UUID("40000000-0000-0000-0000-000000000002")
METER_A = uuid.UUID("50000000-0000-0000-0000-000000000001")
METER_B = uuid.UUID("50000000-0000-0000-0000-000000000002")
ASSET_A = uuid.UUID("60000000-0000-0000-0000-000000000001")


@pytest.fixture
def seeded_registry(db_session: Session) -> dict[str, uuid.UUID]:
    """Create the sites, meters and asset the telemetry payloads reference.

    Two sites so the isolation test has something real to isolate.
    """
    owner = User(
        display_name="Telemetry API Test Owner",
        role=UserRole.PROSUMER,
        status=UserStatus.ACTIVE,
        email=f"telemetry-api-{uuid.uuid4().hex[:8]}@example.org",
    )
    db_session.add(owner)
    db_session.flush()

    for site_id, name in ((SITE_A, "Telemetry Site A"), (SITE_B, "Telemetry Site B")):
        db_session.add(Site(id=site_id, owner_user_id=owner.id, name=name))
    for meter_id, site_id in ((METER_A, SITE_A), (METER_B, SITE_B)):
        db_session.add(
            Meter(
                id=meter_id,
                site_id=site_id,
                meter_type=MeterType.SMART_METER,
                external_meter_ref=f"api-test-{meter_id.hex[-8:]}",
            )
        )
    db_session.add(
        EnergyAsset(
            id=ASSET_A,
            site_id=SITE_A,
            asset_type=EnergyAssetType.PV,
            capacity_kw=Decimal("5.000"),
            status=EnergyAssetStatus.ACTIVE,
        )
    )
    db_session.flush()
    return {"site_a": SITE_A, "site_b": SITE_B, "meter_a": METER_A, "meter_b": METER_B}


@pytest.fixture
def telemetry_client(
    db_session: Session, seeded_registry: dict[str, uuid.UUID]
) -> Iterator[TestClient]:
    """TestClient for Telemetry API endpoints, isolated to one transaction."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def sample_site_id() -> str:
    """Deterministic UUID for a test site."""
    return str(SITE_A)


@pytest.fixture
def sample_meter_id() -> str:
    """Deterministic UUID for a test meter."""
    return str(METER_A)


@pytest.fixture
def sample_asset_id() -> str:
    """Deterministic UUID for a test solar asset."""
    return str(ASSET_A)


@pytest.fixture
def make_reading_payload(
    sample_site_id: str, sample_meter_id: str, sample_asset_id: str
) -> Callable[..., dict[str, Any]]:
    """Factory generating normalized telemetry reading payloads per docs/04_DATA_MODEL.md."""

    def _make(**overrides: Any) -> dict[str, Any]:
        now = datetime.now(UTC).replace(microsecond=0)
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
            # `source` names the ingestion channel, not the device type. The
            # locked vocabulary is meter|inverter|simulator|import|manual
            # (docs/04_DATA_MODEL.md entity 10); "smart_meter" is a MeterType.
            "source": "meter",
        }
        defaults.update(overrides)
        return defaults

    return _make


@pytest.fixture
def make_batch_payloads(
    make_reading_payload: Callable[..., dict[str, Any]],
) -> Callable[[int], list[dict[str, Any]]]:
    """Factory generating a sequence of consecutive 5-minute interval readings.

    Two properties matter here:

    * **Anchored to the present**, not to a hard-coded calendar date. Telemetry
      is classified against its age, so a fixed date drifts further into
      `stale` every day the suite is not run, silently changing what these
      tests exercise.
    * **Five-minute spacing**, so the whole batch sits inside the locked
      15-minute staleness window. At 15-minute spacing every reading but the
      newest is necessarily `stale`, leaving the aggregation tests nothing
      usable to aggregate — the quality rule would mask what they are about.
    """

    def _make(count: int = 4) -> list[dict[str, Any]]:
        step = timedelta(minutes=5)
        base_time = datetime.now(UTC).replace(second=0, microsecond=0) - step * (count - 1)
        batch = []
        for i in range(count):
            t = base_time + step * i
            t_start = t - step
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
