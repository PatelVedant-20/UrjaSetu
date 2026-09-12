"""Phase 1: identity and asset registry persistence.

Proves the entities of docs/04_DATA_MODEL.md persist in PostgreSQL with the
relationships, constraints and indexes the data model requires — and that
integrity is enforced by the database, not merely by application code.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

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
    InverterProtocol,
    MeterType,
    UserRole,
    UserStatus,
    VerificationLevel,
    VerificationSource,
    VerificationStatus,
    VerificationType,
)

PHASE_1_TABLES = {
    "users",
    "utility_accounts",
    "consents",
    "grid_nodes",
    "sites",
    "meters",
    "energy_assets",
    "inverter_devices",
    "verification_records",
}


# ---------------------------------------------------------------------------
# Entity creation
# ---------------------------------------------------------------------------


def test_all_phase_1_tables_exist(engine) -> None:  # type: ignore[no-untyped-def]
    assert PHASE_1_TABLES.issubset(set(inspect(engine).get_table_names()))


def test_create_user(make_user: Callable[..., User]) -> None:
    user = make_user(display_name="Asha Patel", role=UserRole.PROSUMER)

    assert isinstance(user.id, uuid.UUID)
    assert user.role is UserRole.PROSUMER
    assert user.status is UserStatus.ACTIVE
    # docs/00_PROJECT_BIBLE.md section 6: timestamps are timezone-aware UTC.
    assert user.created_at.tzinfo is not None
    assert user.updated_at.tzinfo is not None


def test_create_user_without_email(make_user: Callable[..., User]) -> None:
    """Email is nullable for demo auth modes (docs/04_DATA_MODEL.md entity 1)."""
    user = make_user(email=None)
    assert user.email is None


def test_create_utility_account(make_utility_account: Callable[..., UtilityAccount]) -> None:
    account = make_utility_account(discom_code="PVVNL")

    assert isinstance(account.id, uuid.UUID)
    assert account.discom_code == "PVVNL"
    assert account.verification_level is VerificationLevel.NONE
    assert account.verified_at is None


def test_create_grid_node(make_grid_node: Callable[..., GridNode]) -> None:
    node = make_grid_node(node_type=GridNodeType.TRANSFORMER, nominal_voltage_kv=Decimal("11.0000"))

    assert node.node_type is GridNodeType.TRANSFORMER
    assert node.nominal_voltage_kv == Decimal("11.0000")


def test_create_site(make_site: Callable[..., Site]) -> None:
    site = make_site(name="Gandhinagar Community Roof")

    assert site.name == "Gandhinagar Community Roof"
    assert site.timezone == "Asia/Kolkata"
    # A site can exist before it is mapped onto the digital twin.
    assert site.grid_node_id is None


def test_create_meter(make_meter: Callable[..., Meter]) -> None:
    meter = make_meter(meter_type=MeterType.SMART_METER)

    assert meter.meter_type is MeterType.SMART_METER
    assert meter.active is True
    assert meter.verification_level is VerificationLevel.NONE


def test_create_energy_asset(make_energy_asset: Callable[..., EnergyAsset]) -> None:
    asset = make_energy_asset(capacity_kw=Decimal("7.500"))

    assert asset.asset_type is EnergyAssetType.PV
    # kW held as Numeric, not float — it feeds settlement arithmetic later.
    assert asset.capacity_kw == Decimal("7.500")
    assert isinstance(asset.capacity_kw, Decimal)


def test_create_inverter(make_inverter: Callable[..., InverterDevice]) -> None:
    inverter = make_inverter(protocol=InverterProtocol.SUNSPEC_MODBUS_TCP)

    assert inverter.protocol is InverterProtocol.SUNSPEC_MODBUS_TCP
    # The adapter is named, not imported: Phase 1 adds no device dependency.
    assert inverter.adapter_type == "simulator_adapter"


def test_create_verification_record(make_verification: Callable[..., VerificationRecord]) -> None:
    record = make_verification(verification_type=VerificationType.UTILITY_ACCOUNT)

    assert record.verification_type is VerificationType.UTILITY_ACCOUNT
    assert record.source is VerificationSource.DISCOM
    assert record.status is VerificationStatus.VERIFIED
    assert record.asset_id is None


def test_create_consent(make_consent: Callable[..., Consent]) -> None:
    consent = make_consent(scope=ConsentScope.MARKET_PARTICIPATION)

    assert consent.scope is ConsentScope.MARKET_PARTICIPATION
    assert consent.revoked_at is None
    assert consent.is_active is True


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


def test_user_to_sites_relationship(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    user = make_user()
    make_site(owner_user_id=user.id, name="Roof A")
    make_site(owner_user_id=user.id, name="Roof B")

    db_session.refresh(user)

    assert {site.name for site in user.sites} == {"Roof A", "Roof B"}
    assert all(site.owner.id == user.id for site in user.sites)


def test_site_to_meters_and_assets(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_energy_asset: Callable[..., EnergyAsset],
) -> None:
    site = make_site()
    make_meter(site_id=site.id)
    make_energy_asset(site_id=site.id)

    db_session.refresh(site)

    assert len(site.meters) == 1
    assert len(site.energy_assets) == 1
    assert site.meters[0].site.id == site.id


def test_energy_asset_to_inverters(
    db_session: Session,
    make_energy_asset: Callable[..., EnergyAsset],
    make_inverter: Callable[..., InverterDevice],
) -> None:
    asset = make_energy_asset()
    make_inverter(energy_asset_id=asset.id)
    make_inverter(energy_asset_id=asset.id)

    db_session.refresh(asset)

    assert len(asset.inverters) == 2
    assert all(inv.energy_asset.id == asset.id for inv in asset.inverters)


def test_user_to_utility_accounts_and_consents(
    db_session: Session,
    make_user: Callable[..., User],
    make_utility_account: Callable[..., UtilityAccount],
    make_consent: Callable[..., Consent],
) -> None:
    user = make_user()
    make_utility_account(user_id=user.id)
    make_consent(user_id=user.id, scope=ConsentScope.METER_DATA)
    make_consent(user_id=user.id, scope=ConsentScope.MARKET_PARTICIPATION)

    db_session.refresh(user)

    assert len(user.utility_accounts) == 1
    assert {c.scope for c in user.consents} == {
        ConsentScope.METER_DATA,
        ConsentScope.MARKET_PARTICIPATION,
    }


def test_site_to_grid_node(
    db_session: Session, make_grid_node: Callable[..., GridNode], make_site: Callable[..., Site]
) -> None:
    node = make_grid_node()
    site = make_site(grid_node_id=node.id)

    db_session.refresh(node)

    assert site.grid_node is not None
    assert site.grid_node.id == node.id
    assert [s.id for s in node.sites] == [site.id]


def test_grid_node_self_reference(
    db_session: Session, make_grid_node: Callable[..., GridNode]
) -> None:
    """Radial topology: substation -> feeder -> connection point."""
    substation = make_grid_node(node_type=GridNodeType.SUBSTATION)
    feeder = make_grid_node(node_type=GridNodeType.FEEDER, parent_node_id=substation.id)
    point = make_grid_node(node_type=GridNodeType.CONNECTION_POINT, parent_node_id=feeder.id)

    db_session.refresh(substation)
    db_session.refresh(feeder)

    assert point.parent is not None
    assert point.parent.id == feeder.id
    assert feeder.parent is not None
    assert feeder.parent.id == substation.id
    assert [child.id for child in substation.children] == [feeder.id]


def test_verification_record_can_target_an_asset(
    make_energy_asset: Callable[..., EnergyAsset],
    make_verification: Callable[..., VerificationRecord],
) -> None:
    asset = make_energy_asset()
    record = make_verification(
        user_id=asset.site.owner_user_id,
        asset_id=asset.id,
        verification_type=VerificationType.ENERGY_ASSET,
    )

    assert record.energy_asset is not None
    assert record.energy_asset.id == asset.id


# ---------------------------------------------------------------------------
# Foreign keys
# ---------------------------------------------------------------------------


def test_site_requires_an_existing_owner(db_session: Session) -> None:
    db_session.add(Site(owner_user_id=uuid.uuid4(), name="Orphan"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_meter_requires_an_existing_site(db_session: Session) -> None:
    db_session.add(Meter(site_id=uuid.uuid4(), meter_type=MeterType.NET_METER))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_inverter_requires_an_existing_asset(db_session: Session) -> None:
    db_session.add(InverterDevice(energy_asset_id=uuid.uuid4()))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_verification_requires_an_existing_user(db_session: Session) -> None:
    db_session.add(
        VerificationRecord(
            user_id=uuid.uuid4(),
            verification_type=VerificationType.IDENTITY,
            source=VerificationSource.SELF_DECLARED,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_user_with_sites_is_blocked(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    """RESTRICT: sites, meters and assets must not vanish with the user."""
    user = make_user()
    make_site(owner_user_id=user.id)

    # Raw DML raises at execute time, not at the next flush.
    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})


def test_deleting_a_site_cascades_to_meters_and_assets(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_energy_asset: Callable[..., EnergyAsset],
    make_inverter: Callable[..., InverterDevice],
) -> None:
    """CASCADE: site-scoped equipment has no meaning without its site."""
    site = make_site()
    make_meter(site_id=site.id)
    asset = make_energy_asset(site_id=site.id)
    make_inverter(energy_asset_id=asset.id)
    site_id = site.id

    db_session.execute(text("DELETE FROM sites WHERE id = :sid"), {"sid": site_id})
    db_session.flush()

    remaining_meters = db_session.execute(
        text("SELECT count(*) FROM meters WHERE site_id = :sid"), {"sid": site_id}
    ).scalar_one()
    remaining_inverters = db_session.execute(
        text("SELECT count(*) FROM inverter_devices WHERE energy_asset_id = :aid"),
        {"aid": asset.id},
    ).scalar_one()

    assert remaining_meters == 0
    assert remaining_inverters == 0


def test_deleting_a_grid_node_with_sites_is_blocked(
    db_session: Session, make_grid_node: Callable[..., GridNode], make_site: Callable[..., Site]
) -> None:
    node = make_grid_node()
    make_site(grid_node_id=node.id)

    with pytest.raises(IntegrityError):
        db_session.execute(text("DELETE FROM grid_nodes WHERE id = :nid"), {"nid": node.id})


# ---------------------------------------------------------------------------
# Unique constraints
# ---------------------------------------------------------------------------


def test_user_email_is_unique(db_session: Session, make_user: Callable[..., User]) -> None:
    user = make_user()
    db_session.add(User(email=user.email, display_name="Impostor", role=UserRole.CONSUMER))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_multiple_users_may_have_no_email(make_user: Callable[..., User]) -> None:
    """PostgreSQL allows many NULLs under a unique constraint — demo mode needs that."""
    make_user(email=None)
    make_user(email=None)


def test_grid_node_external_ref_is_unique(
    db_session: Session, make_grid_node: Callable[..., GridNode]
) -> None:
    node = make_grid_node()
    db_session.add(
        GridNode(
            external_ref=node.external_ref,
            node_type=GridNodeType.FEEDER,
            nominal_voltage_kv=Decimal("11.0"),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_meter_external_ref_is_unique(
    db_session: Session, make_meter: Callable[..., Meter], make_site: Callable[..., Site]
) -> None:
    """Two sites must not claim the same physical meter — it would double-count energy."""
    meter = make_meter()
    other_site = make_site()
    db_session.add(
        Meter(
            site_id=other_site.id,
            meter_type=MeterType.NET_METER,
            external_meter_ref=meter.external_meter_ref,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_utility_account_consumer_number_is_unique_per_discom(
    db_session: Session,
    make_utility_account: Callable[..., UtilityAccount],
    make_user: Callable[..., User],
) -> None:
    account = make_utility_account()
    other_user = make_user()
    db_session.add(
        UtilityAccount(
            user_id=other_user.id,
            discom_code=account.discom_code,
            consumer_number_hash=account.consumer_number_hash,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_consumer_number_allowed_across_different_discoms(
    make_utility_account: Callable[..., UtilityAccount],
) -> None:
    account = make_utility_account(discom_code="PVVNL")
    make_utility_account(discom_code="BRPL", consumer_number_hash=account.consumer_number_hash)


# ---------------------------------------------------------------------------
# Check constraints
# ---------------------------------------------------------------------------


def test_energy_asset_capacity_must_be_positive(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    db_session.add(
        EnergyAsset(
            site_id=make_site().id,
            asset_type=EnergyAssetType.PV,
            capacity_kw=Decimal("0"),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_grid_node_voltage_must_be_positive(db_session: Session) -> None:
    db_session.add(
        GridNode(
            external_ref=f"bad-{uuid.uuid4().hex[:8]}",
            node_type=GridNodeType.FEEDER,
            nominal_voltage_kv=Decimal("-11.0"),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_grid_node_cannot_be_its_own_parent(
    db_session: Session, make_grid_node: Callable[..., GridNode]
) -> None:
    node = make_grid_node()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE grid_nodes SET parent_node_id = id WHERE id = :nid"), {"nid": node.id}
        )


def test_site_latitude_must_be_in_range(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    db_session.add(Site(owner_user_id=make_user().id, name="Impossible", latitude=Decimal("91.0")))

    with pytest.raises((IntegrityError, DataError)):
        db_session.flush()


def test_site_name_cannot_be_blank(db_session: Session, make_user: Callable[..., User]) -> None:
    db_session.add(Site(owner_user_id=make_user().id, name="   "))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_consent_cannot_be_revoked_before_it_was_granted(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    granted = datetime(2026, 3, 1, tzinfo=UTC)
    db_session.add(
        Consent(
            user_id=make_user().id,
            scope=ConsentScope.METER_DATA,
            granted_at=granted,
            revoked_at=granted - timedelta(days=1),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_verification_cannot_expire_before_it_was_verified(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    verified = datetime(2026, 3, 1, tzinfo=UTC)
    db_session.add(
        VerificationRecord(
            user_id=make_user().id,
            verification_type=VerificationType.IDENTITY,
            source=VerificationSource.DISCOM,
            status=VerificationStatus.VERIFIED,
            verified_at=verified,
            expires_at=verified - timedelta(days=1),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_verified_status_requires_a_verified_at(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    """A record cannot claim VERIFIED without recording when."""
    db_session.add(
        VerificationRecord(
            user_id=make_user().id,
            verification_type=VerificationType.IDENTITY,
            source=VerificationSource.DISCOM,
            status=VerificationStatus.VERIFIED,
            verified_at=None,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# Enum persistence
# ---------------------------------------------------------------------------


def test_enums_persist_as_lowercase_values(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    """The database stores `prosumer`, not the member name `PROSUMER`.

    The API contract and the data model both speak lowercase; if SQLAlchemy
    fell back to member names, every payload would be wrong.
    """
    user = make_user(role=UserRole.PROSUMER, status=UserStatus.ACTIVE)

    row = db_session.execute(
        text("SELECT role::text, status::text FROM users WHERE id = :uid"), {"uid": user.id}
    ).one()

    assert row == ("prosumer", "active")


def test_invalid_enum_value_is_rejected_by_the_database(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    user = make_user()

    with pytest.raises((IntegrityError, DataError)):
        db_session.execute(
            text("UPDATE users SET role = 'trader' WHERE id = :uid"), {"uid": user.id}
        )


# ---------------------------------------------------------------------------
# Phase 1 gate — the registry half of
# create user -> create site -> attach meter -> add PV -> verify -> eligibility
# ---------------------------------------------------------------------------


def test_phase_1_registry_walkthrough(
    db_session: Session,
    make_user: Callable[..., User],
    make_grid_node: Callable[..., GridNode],
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_energy_asset: Callable[..., EnergyAsset],
    make_inverter: Callable[..., InverterDevice],
    make_utility_account: Callable[..., UtilityAccount],
    make_verification: Callable[..., VerificationRecord],
    make_consent: Callable[..., Consent],
) -> None:
    """Onboard a prosumer end to end and read the whole registry back."""
    verified_at = datetime(2026, 2, 1, tzinfo=UTC)

    user = make_user(display_name="Asha Patel", role=UserRole.PROSUMER)
    make_utility_account(
        user_id=user.id,
        verification_level=VerificationLevel.DISCOM_VERIFIED,
        verified_at=verified_at,
    )
    node = make_grid_node(node_type=GridNodeType.CONNECTION_POINT)
    site = make_site(owner_user_id=user.id, grid_node_id=node.id)
    make_meter(
        site_id=site.id,
        verification_level=VerificationLevel.DISCOM_VERIFIED,
    )
    asset = make_energy_asset(
        site_id=site.id, asset_type=EnergyAssetType.PV, status=EnergyAssetStatus.ACTIVE
    )
    make_inverter(energy_asset_id=asset.id, protocol=InverterProtocol.SUNSPEC_MODBUS_TCP)
    make_verification(
        user_id=user.id,
        asset_id=asset.id,
        verification_type=VerificationType.ENERGY_ASSET,
        verified_at=verified_at,
    )
    make_consent(user_id=user.id, scope=ConsentScope.METER_DATA)
    make_consent(user_id=user.id, scope=ConsentScope.MARKET_PARTICIPATION)

    db_session.expire_all()
    reloaded = db_session.get(User, user.id)

    assert reloaded is not None
    assert len(reloaded.sites) == 1
    registered_site = reloaded.sites[0]
    assert registered_site.grid_node is not None
    assert len(registered_site.meters) == 1
    assert len(registered_site.energy_assets) == 1
    assert len(registered_site.energy_assets[0].inverters) == 1
    assert len(reloaded.utility_accounts) == 1
    assert len(reloaded.verification_records) == 1
    assert len(reloaded.consents) == 2
