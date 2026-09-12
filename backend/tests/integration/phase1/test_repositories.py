"""Phase 1: repository foundations.

Confirms the query layer other phases will build services on top of returns
what it claims, against real PostgreSQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import EnergyAsset, GridNode, Meter, Site, User, UtilityAccount
from app.domain.enums import (
    ConsentScope,
    EnergyAssetType,
    GridNodeType,
    VerificationLevel,
    VerificationStatus,
    VerificationType,
)
from app.repositories import (
    ConsentRepository,
    EnergyAssetRepository,
    GridNodeRepository,
    MeterRepository,
    SiteRepository,
    UserRepository,
    UtilityAccountRepository,
    VerificationRecordRepository,
)


def test_user_repository_get_by_email(db_session: Session, make_user: Callable[..., User]) -> None:
    user = make_user()
    repo = UserRepository(db_session)

    assert user.email is not None
    found = repo.get_by_email(user.email)

    assert found is not None
    assert found.id == user.id
    assert repo.get_by_email("nobody@example.org") is None


def test_base_repository_get_and_exists(
    db_session: Session, make_user: Callable[..., User]
) -> None:
    user = make_user()
    repo = UserRepository(db_session)

    assert repo.get(user.id) is not None
    assert repo.exists(user.id) is True
    assert repo.exists(uuid.uuid4()) is False


def test_site_repository_lists_by_owner(
    db_session: Session, make_user: Callable[..., User], make_site: Callable[..., Site]
) -> None:
    owner = make_user()
    other = make_user()
    make_site(owner_user_id=owner.id)
    make_site(owner_user_id=owner.id)
    make_site(owner_user_id=other.id)

    sites = SiteRepository(db_session).list_for_owner(owner.id)

    assert len(sites) == 2
    assert all(site.owner_user_id == owner.id for site in sites)


def test_site_repository_eager_loads_the_registry(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_energy_asset: Callable[..., EnergyAsset],
    make_inverter: Callable[..., Callable[..., object]],
) -> None:
    site = make_site()
    make_meter(site_id=site.id)
    asset = make_energy_asset(site_id=site.id)
    make_inverter(energy_asset_id=asset.id)

    db_session.expire_all()
    loaded = SiteRepository(db_session).get_with_registry(site.id)

    assert loaded is not None
    assert len(loaded.meters) == 1
    assert len(loaded.energy_assets) == 1
    assert len(loaded.energy_assets[0].inverters) == 1


def test_grid_node_repository_traverses_topology(
    db_session: Session, make_grid_node: Callable[..., GridNode]
) -> None:
    repo = GridNodeRepository(db_session)
    feeder = make_grid_node(node_type=GridNodeType.FEEDER, feeder_id="FEEDER-X")
    make_grid_node(parent_node_id=feeder.id, feeder_id="FEEDER-X")
    make_grid_node(parent_node_id=feeder.id, feeder_id="FEEDER-X")

    assert len(repo.list_children(feeder.id)) == 2
    assert len(repo.list_by_feeder("FEEDER-X")) == 3
    assert repo.get_by_external_ref(feeder.external_ref) is not None


def test_meter_repository_lookups(
    db_session: Session, make_site: Callable[..., Site], make_meter: Callable[..., Meter]
) -> None:
    site = make_site()
    meter = make_meter(site_id=site.id)
    repo = MeterRepository(db_session)

    assert [m.id for m in repo.list_for_site(site.id)] == [meter.id]
    assert meter.external_meter_ref is not None
    assert repo.get_by_external_ref(meter.external_meter_ref) is not None


def test_energy_asset_repository_filters_by_type_and_owner(
    db_session: Session,
    make_user: Callable[..., User],
    make_site: Callable[..., Site],
    make_energy_asset: Callable[..., EnergyAsset],
) -> None:
    owner = make_user()
    site = make_site(owner_user_id=owner.id)
    make_energy_asset(site_id=site.id, asset_type=EnergyAssetType.PV)
    make_energy_asset(site_id=site.id, asset_type=EnergyAssetType.BATTERY)
    repo = EnergyAssetRepository(db_session)

    assert len(repo.list_for_site(site.id)) == 2
    assert len(repo.list_for_site(site.id, asset_type=EnergyAssetType.PV)) == 1
    assert len(repo.list_for_owner(owner.id)) == 2


def test_utility_account_repository_resolves_a_consumer_number(
    db_session: Session, make_utility_account: Callable[..., UtilityAccount]
) -> None:
    account = make_utility_account()
    repo = UtilityAccountRepository(db_session)

    found = repo.get_by_consumer_number_hash(account.discom_code, account.consumer_number_hash)

    assert found is not None
    assert found.id == account.id
    assert repo.get_by_consumer_number_hash("UNKNOWN", "nope") is None


def test_consent_repository_distinguishes_active_from_revoked(
    db_session: Session, make_user: Callable[..., User], make_consent: Callable[..., object]
) -> None:
    user = make_user()
    make_consent(user_id=user.id, scope=ConsentScope.METER_DATA)
    make_consent(
        user_id=user.id,
        scope=ConsentScope.MARKET_PARTICIPATION,
        revoked_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    repo = ConsentRepository(db_session)

    assert len(repo.list_for_user(user.id)) == 2
    assert len(repo.list_active_for_user(user.id)) == 1
    assert repo.has_active_scope(user.id, ConsentScope.METER_DATA) is True
    # Revoked is not active — revocation is a timestamp, not a deletion.
    assert repo.has_active_scope(user.id, ConsentScope.MARKET_PARTICIPATION) is False


def test_verification_repository_returns_only_verified_records(
    db_session: Session,
    make_user: Callable[..., User],
    make_verification: Callable[..., object],
) -> None:
    user = make_user()
    make_verification(
        user_id=user.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.VERIFIED,
        verified_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    make_verification(
        user_id=user.id,
        verification_type=VerificationType.METER,
        status=VerificationStatus.PENDING,
        verification_level=VerificationLevel.NONE,
        verified_at=None,
    )
    repo = VerificationRecordRepository(db_session)

    assert len(repo.list_for_user(user.id)) == 2
    verified = repo.list_verified_for_user(user.id)
    assert len(verified) == 1
    assert verified[0].verification_type is VerificationType.IDENTITY
    assert len(repo.list_verified_for_user(user.id, verification_type=VerificationType.METER)) == 0
