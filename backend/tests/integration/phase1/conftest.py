"""Factory fixtures for the Phase 1 identity and asset registry.

Each factory persists through the rolled-back `db_session` from the root
conftest, so tests share no state. Factories default to a *valid* entity and
take overrides, which keeps each test's setup to the one field it is actually
about.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import (
    Consent,
    EnergyAsset,
    GridNode,
    InverterDevice,
    Meter,
    Site,
    User,
    UtilityAccount,
    VerificationRecord,
)
from app.domain.enums import (
    ConsentScope,
    EnergyAssetStatus,
    EnergyAssetType,
    GridNodeType,
    MeterType,
    UserRole,
    UserStatus,
    VerificationLevel,
    VerificationSource,
    VerificationStatus,
    VerificationType,
)
from app.main import create_app


def _unique(prefix: str) -> str:
    """A collision-free suffix so unique constraints don't trip across tests."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def api_client(db_session: Session) -> Iterator[TestClient]:
    """HTTP client whose requests run inside the test's rolled-back transaction.

    Overriding `get_db` with the test session is what keeps API tests isolated:
    services legitimately call `session.commit()`, and because the session is
    joined to an outer transaction SQLAlchemy turns that into a savepoint
    release, so the outer rollback still discards everything afterwards.
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session: Session) -> Callable[..., User]:
    def _make(**overrides: Any) -> User:
        defaults: dict[str, Any] = {
            "email": f"{_unique('user')}@example.org",
            "display_name": "Test Prosumer",
            "role": UserRole.PROSUMER,
            "status": UserStatus.ACTIVE,
        }
        user = User(**{**defaults, **overrides})
        db_session.add(user)
        db_session.flush()
        return user

    return _make


@pytest.fixture
def make_grid_node(db_session: Session) -> Callable[..., GridNode]:
    def _make(**overrides: Any) -> GridNode:
        defaults: dict[str, Any] = {
            "external_ref": _unique("node"),
            "node_type": GridNodeType.CONNECTION_POINT,
            "nominal_voltage_kv": Decimal("0.4000"),
            "feeder_id": "FEEDER-01",
        }
        node = GridNode(**{**defaults, **overrides})
        db_session.add(node)
        db_session.flush()
        return node

    return _make


@pytest.fixture
def make_site(db_session: Session, make_user: Callable[..., User]) -> Callable[..., Site]:
    def _make(**overrides: Any) -> Site:
        if "owner_user_id" not in overrides and "owner" not in overrides:
            overrides["owner_user_id"] = make_user().id
        defaults: dict[str, Any] = {
            "name": "Ahmedabad Rooftop",
            # Ahmedabad, demo-safe approximation.
            "latitude": Decimal("23.022500"),
            "longitude": Decimal("72.571400"),
            "timezone": "Asia/Kolkata",
        }
        site = Site(**{**defaults, **overrides})
        db_session.add(site)
        db_session.flush()
        return site

    return _make


@pytest.fixture
def make_meter(db_session: Session, make_site: Callable[..., Site]) -> Callable[..., Meter]:
    def _make(**overrides: Any) -> Meter:
        if "site_id" not in overrides and "site" not in overrides:
            overrides["site_id"] = make_site().id
        defaults: dict[str, Any] = {
            "meter_type": MeterType.NET_METER,
            "vendor": "Secure Meters",
            "external_meter_ref": _unique("meter"),
            "verification_level": VerificationLevel.NONE,
            "active": True,
        }
        meter = Meter(**{**defaults, **overrides})
        db_session.add(meter)
        db_session.flush()
        return meter

    return _make


@pytest.fixture
def make_energy_asset(
    db_session: Session, make_site: Callable[..., Site]
) -> Callable[..., EnergyAsset]:
    def _make(**overrides: Any) -> EnergyAsset:
        if "site_id" not in overrides and "site" not in overrides:
            overrides["site_id"] = make_site().id
        defaults: dict[str, Any] = {
            "asset_type": EnergyAssetType.PV,
            "capacity_kw": Decimal("5.000"),
            "status": EnergyAssetStatus.ACTIVE,
            "commissioned_at": datetime(2026, 1, 15, tzinfo=UTC),
        }
        asset = EnergyAsset(**{**defaults, **overrides})
        db_session.add(asset)
        db_session.flush()
        return asset

    return _make


@pytest.fixture
def make_inverter(
    db_session: Session, make_energy_asset: Callable[..., EnergyAsset]
) -> Callable[..., InverterDevice]:
    def _make(**overrides: Any) -> InverterDevice:
        if "energy_asset_id" not in overrides and "energy_asset" not in overrides:
            overrides["energy_asset_id"] = make_energy_asset().id
        defaults: dict[str, Any] = {
            "manufacturer": "Delta",
            "model": "RPI-M6A",
            "external_device_ref": _unique("inv"),
            "adapter_type": "simulator_adapter",
        }
        inverter = InverterDevice(**{**defaults, **overrides})
        db_session.add(inverter)
        db_session.flush()
        return inverter

    return _make


@pytest.fixture
def make_utility_account(
    db_session: Session, make_user: Callable[..., User]
) -> Callable[..., UtilityAccount]:
    def _make(**overrides: Any) -> UtilityAccount:
        if "user_id" not in overrides and "user" not in overrides:
            overrides["user_id"] = make_user().id
        defaults: dict[str, Any] = {
            "discom_code": "TORRENT-AMD",
            # A hash, never a raw consumer number (docs/04_DATA_MODEL.md).
            "consumer_number_hash": _unique("sha256"),
            "verification_level": VerificationLevel.NONE,
        }
        account = UtilityAccount(**{**defaults, **overrides})
        db_session.add(account)
        db_session.flush()
        return account

    return _make


@pytest.fixture
def make_consent(db_session: Session, make_user: Callable[..., User]) -> Callable[..., Consent]:
    def _make(**overrides: Any) -> Consent:
        if "user_id" not in overrides and "user" not in overrides:
            overrides["user_id"] = make_user().id
        defaults: dict[str, Any] = {
            "scope": ConsentScope.METER_DATA,
            "granted_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
        consent = Consent(**{**defaults, **overrides})
        db_session.add(consent)
        db_session.flush()
        return consent

    return _make


@pytest.fixture
def make_verification(
    db_session: Session, make_user: Callable[..., User]
) -> Callable[..., VerificationRecord]:
    def _make(**overrides: Any) -> VerificationRecord:
        if "user_id" not in overrides and "user" not in overrides:
            overrides["user_id"] = make_user().id
        defaults: dict[str, Any] = {
            "verification_type": VerificationType.IDENTITY,
            "source": VerificationSource.DISCOM,
            "verification_level": VerificationLevel.DISCOM_VERIFIED,
            "status": VerificationStatus.VERIFIED,
            "verified_at": datetime(2026, 2, 1, tzinfo=UTC),
        }
        record = VerificationRecord(**{**defaults, **overrides})
        db_session.add(record)
        db_session.flush()
        return record

    return _make
