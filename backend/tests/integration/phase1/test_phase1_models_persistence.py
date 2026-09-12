"""Phase 1 persistence tests: Identity and Asset Registry domain models.

Verifies the requirements of docs/04_DATA_MODEL.md, docs/00_PROJECT_BIBLE.md (section 6),
and docs/07_CODING_PHASES.md (Phase 1):
  1. User persistence
  2. Utility account persistence
  3. Site persistence
  4. Grid node persistence
  5. Meter persistence
  6. Energy asset persistence
  7. Inverter persistence
  8. Verification record persistence
  9. Consent persistence
  10. UUID primary keys
  11. Timezone-aware UTC timestamps
  12. Unique constraints
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db.models as models


def _get_model(name: str) -> Any:
    """Helper to safely fetch a model class from app.db.models or fail with a clear message."""
    model_cls = getattr(models, name, None)
    if model_cls is None:
        pytest.fail(
            f"Required domain model '{name}' is not exported by app.db.models. "
            f"Check docs/04_DATA_MODEL.md for the specification.",
            pytrace=False,
        )
    return model_cls


# ---------------------------------------------------------------------------
# 1. User Persistence
# ---------------------------------------------------------------------------


class TestUserPersistence:
    """Verify persistence of the `users` entity."""

    def test_user_model_is_registered(self) -> None:
        user_cls = _get_model("User")
        assert user_cls.__tablename__ == "users"

    def test_create_user_with_required_fields(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        user = user_cls(
            email=f"user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Test Prosumer",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        persisted = db_session.query(user_cls).filter_by(id=user.id).one()
        assert persisted.display_name == "Test Prosumer"
        assert persisted.role == "prosumer"
        assert persisted.status == "active"
        assert isinstance(persisted.id, uuid.UUID)
        assert persisted.created_at is not None
        assert persisted.created_at.tzinfo is not None
        assert persisted.updated_at is not None
        assert persisted.updated_at.tzinfo is not None

    def test_user_email_nullable_for_demo_modes(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        user = user_cls(
            email=None,
            display_name="Anonymous Demo Prosumer",
            role="consumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        persisted = db_session.query(user_cls).filter_by(id=user.id).one()
        assert persisted.email is None

    def test_user_email_unique_constraint(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        shared_email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
        user1 = user_cls(
            email=shared_email,
            display_name="User 1",
            role="consumer",
            status="active",
        )
        db_session.add(user1)
        db_session.flush()

        user2 = user_cls(
            email=shared_email,
            display_name="User 2",
            role="prosumer",
            status="active",
        )
        db_session.add(user2)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_user_roles_supported(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        roles = ["consumer", "prosumer", "operator", "regulator_viewer", "admin"]
        for role in roles:
            user = user_cls(
                email=f"{role}_{uuid.uuid4().hex[:8]}@example.com",
                display_name=f"{role.capitalize()} User",
                role=role,
                status="active",
            )
            db_session.add(user)
            db_session.flush()
            assert user.role == role


# ---------------------------------------------------------------------------
# 2. Utility Account Persistence
# ---------------------------------------------------------------------------


class TestUtilityAccountPersistence:
    """Verify persistence of the `utility_accounts` entity."""

    def test_utility_account_model_is_registered(self) -> None:
        cls = _get_model("UtilityAccount")
        assert cls.__tablename__ == "utility_accounts"

    def test_create_utility_account(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        acc_cls = _get_model("UtilityAccount")

        user = user_cls(
            email=f"util_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Utility User",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        now = datetime.now(UTC)
        account = acc_cls(
            user_id=user.id,
            discom_code="BESCOM",
            consumer_number_hash="hash_e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            verification_level="discom_verified",
            verified_at=now,
        )
        db_session.add(account)
        db_session.flush()

        persisted = db_session.query(acc_cls).filter_by(id=account.id).one()
        assert persisted.discom_code == "BESCOM"
        assert persisted.user_id == user.id
        assert isinstance(persisted.id, uuid.UUID)
        assert persisted.verified_at is not None
        assert persisted.verified_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 3. Grid Node Persistence
# ---------------------------------------------------------------------------


class TestGridNodePersistence:
    """Verify persistence of the `grid_nodes` entity."""

    def test_grid_node_model_is_registered(self) -> None:
        cls = _get_model("GridNode")
        assert cls.__tablename__ == "grid_nodes"

    def test_create_grid_node(self, db_session: Session) -> None:
        node_cls = _get_model("GridNode")
        ext_ref = f"NODE_{uuid.uuid4().hex[:8]}"

        node = node_cls(
            external_ref=ext_ref,
            node_type="transformer",
            nominal_voltage_kv=11.0,
            feeder_id="FEEDER_NORTH_01",
        )
        db_session.add(node)
        db_session.flush()

        persisted = db_session.query(node_cls).filter_by(id=node.id).one()
        assert persisted.external_ref == ext_ref
        assert persisted.node_type == "transformer"
        assert persisted.nominal_voltage_kv == 11.0
        assert persisted.feeder_id == "FEEDER_NORTH_01"
        assert isinstance(persisted.id, uuid.UUID)

    def test_grid_node_external_ref_unique(self, db_session: Session) -> None:
        node_cls = _get_model("GridNode")
        ext_ref = f"UNIQUE_NODE_{uuid.uuid4().hex[:8]}"

        node1 = node_cls(
            external_ref=ext_ref,
            node_type="substation",
            nominal_voltage_kv=33.0,
        )
        db_session.add(node1)
        db_session.flush()

        node2 = node_cls(
            external_ref=ext_ref,
            node_type="connection_point",
            nominal_voltage_kv=11.0,
        )
        db_session.add(node2)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ---------------------------------------------------------------------------
# 4. Site Persistence
# ---------------------------------------------------------------------------


class TestSitePersistence:
    """Verify persistence of the `sites` entity."""

    def test_site_model_is_registered(self) -> None:
        cls = _get_model("Site")
        assert cls.__tablename__ == "sites"

    def test_create_site(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        node_cls = _get_model("GridNode")
        site_cls = _get_model("Site")

        user = user_cls(
            email=f"site_owner_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Site Owner",
            role="prosumer",
            status="active",
        )
        node = node_cls(
            external_ref=f"NODE_SITE_{uuid.uuid4().hex[:8]}",
            node_type="connection_point",
            nominal_voltage_kv=0.415,
        )
        db_session.add_all([user, node])
        db_session.flush()

        site = site_cls(
            owner_user_id=user.id,
            name="Green Meadows Solar Villa #4",
            latitude=12.9716,
            longitude=77.5946,
            grid_node_id=node.id,
            timezone="Asia/Kolkata",
        )
        db_session.add(site)
        db_session.flush()

        persisted = db_session.query(site_cls).filter_by(id=site.id).one()
        assert persisted.name == "Green Meadows Solar Villa #4"
        assert persisted.owner_user_id == user.id
        assert persisted.grid_node_id == node.id
        assert persisted.timezone == "Asia/Kolkata"
        assert isinstance(persisted.id, uuid.UUID)
        assert persisted.created_at is not None
        assert persisted.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# 5. Meter Persistence
# ---------------------------------------------------------------------------


class TestMeterPersistence:
    """Verify persistence of the `meters` entity."""

    def test_meter_model_is_registered(self) -> None:
        cls = _get_model("Meter")
        assert cls.__tablename__ == "meters"

    def test_create_meter(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")
        meter_cls = _get_model("Meter")

        user = user_cls(
            email=f"meter_user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Meter User",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        site = site_cls(
            owner_user_id=user.id,
            name="Apartment 101",
            timezone="Asia/Kolkata",
        )
        db_session.add(site)
        db_session.flush()

        ext_ref = f"MTR_{uuid.uuid4().hex[:8]}"
        meter = meter_cls(
            site_id=site.id,
            meter_type="net_meter",
            vendor="Schneider Electric",
            external_meter_ref=ext_ref,
            verification_level="discom_verified",
            active=True,
        )
        db_session.add(meter)
        db_session.flush()

        persisted = db_session.query(meter_cls).filter_by(id=meter.id).one()
        assert persisted.external_meter_ref == ext_ref
        assert persisted.meter_type == "net_meter"
        assert persisted.active is True
        assert isinstance(persisted.id, uuid.UUID)

    def test_meter_external_ref_unique(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")
        meter_cls = _get_model("Meter")

        user = user_cls(
            email=f"meter_unique_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Meter Unique User",
            role="consumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        site = site_cls(
            owner_user_id=user.id,
            name="Commercial Site",
            timezone="Asia/Kolkata",
        )
        db_session.add(site)
        db_session.flush()

        ext_ref = f"MTR_SHARED_{uuid.uuid4().hex[:8]}"
        m1 = meter_cls(
            site_id=site.id,
            meter_type="smart_meter",
            vendor="L&T",
            external_meter_ref=ext_ref,
            verification_level="self_declared",
            active=True,
        )
        db_session.add(m1)
        db_session.flush()

        m2 = meter_cls(
            site_id=site.id,
            meter_type="gross_meter",
            vendor="Genus",
            external_meter_ref=ext_ref,
            verification_level="self_declared",
            active=True,
        )
        db_session.add(m2)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ---------------------------------------------------------------------------
# 6. Energy Asset Persistence
# ---------------------------------------------------------------------------


class TestEnergyAssetPersistence:
    """Verify persistence of the `energy_assets` entity."""

    def test_energy_asset_model_is_registered(self) -> None:
        cls = _get_model("EnergyAsset")
        assert cls.__tablename__ == "energy_assets"

    def test_create_solar_asset(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")
        asset_cls = _get_model("EnergyAsset")

        user = user_cls(
            email=f"asset_user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Solar Prosumer",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        site = site_cls(
            owner_user_id=user.id,
            name="Rooftop Solar Plant #1",
            timezone="Asia/Kolkata",
        )
        db_session.add(site)
        db_session.flush()

        now = datetime.now(UTC)
        asset = asset_cls(
            site_id=site.id,
            asset_type="pv",
            capacity_kw=10.5,
            commissioned_at=now,
            status="active",
        )
        db_session.add(asset)
        db_session.flush()

        persisted = db_session.query(asset_cls).filter_by(id=asset.id).one()
        assert persisted.asset_type == "pv"
        assert float(persisted.capacity_kw) == 10.5
        assert persisted.status == "active"
        assert isinstance(persisted.id, uuid.UUID)


# ---------------------------------------------------------------------------
# 7. Inverter Persistence
# ---------------------------------------------------------------------------


class TestInverterDevicePersistence:
    """Verify persistence of the `inverter_devices` entity."""

    def test_inverter_device_model_is_registered(self) -> None:
        cls = _get_model("InverterDevice")
        assert cls.__tablename__ == "inverter_devices"

    def test_create_inverter_device(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")
        asset_cls = _get_model("EnergyAsset")
        inv_cls = _get_model("InverterDevice")

        user = user_cls(
            email=f"inv_user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Inverter User",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        site = site_cls(
            owner_user_id=user.id,
            name="Solar Farm #1",
            timezone="Asia/Kolkata",
        )
        db_session.add(site)
        db_session.flush()

        asset = asset_cls(
            site_id=site.id,
            asset_type="pv",
            capacity_kw=15.0,
            status="active",
        )
        db_session.add(asset)
        db_session.flush()

        ext_ref = f"INV_{uuid.uuid4().hex[:8]}"
        inverter = inv_cls(
            energy_asset_id=asset.id,
            manufacturer="SMA Solar",
            model="Sunny Boy 5.0",
            protocol="sunspec_modbus_tcp",
            external_device_ref=ext_ref,
            adapter_type="sunspec_modbus_tcp",
        )
        db_session.add(inverter)
        db_session.flush()

        persisted = db_session.query(inv_cls).filter_by(id=inverter.id).one()
        assert persisted.external_device_ref == ext_ref
        assert persisted.manufacturer == "SMA Solar"
        assert persisted.protocol == "sunspec_modbus_tcp"
        assert isinstance(persisted.id, uuid.UUID)

    def test_inverter_external_device_ref_unique(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")
        asset_cls = _get_model("EnergyAsset")
        inv_cls = _get_model("InverterDevice")

        user = user_cls(
            email=f"inv_uniq_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Inverter Uniq User",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        site = site_cls(owner_user_id=user.id, name="Solar Site", timezone="Asia/Kolkata")
        db_session.add(site)
        db_session.flush()

        asset = asset_cls(site_id=site.id, asset_type="pv", capacity_kw=5.0, status="active")
        db_session.add(asset)
        db_session.flush()

        ext_ref = f"INV_SHARED_{uuid.uuid4().hex[:8]}"
        i1 = inv_cls(
            energy_asset_id=asset.id,
            manufacturer="SolarEdge",
            model="SE5000H",
            protocol="sunspec_modbus_tcp",
            external_device_ref=ext_ref,
            adapter_type="sunspec_modbus_tcp",
        )
        db_session.add(i1)
        db_session.flush()

        i2 = inv_cls(
            energy_asset_id=asset.id,
            manufacturer="Growatt",
            model="MIN 5000TL-X",
            protocol="sunspec_modbus_tcp",
            external_device_ref=ext_ref,
            adapter_type="simulator",
        )
        db_session.add(i2)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ---------------------------------------------------------------------------
# 8. Verification Record Persistence
# ---------------------------------------------------------------------------


class TestVerificationRecordPersistence:
    """Verify persistence of the `verification_records` entity."""

    def test_verification_record_model_is_registered(self) -> None:
        cls = _get_model("VerificationRecord")
        assert cls.__tablename__ == "verification_records"

    def test_create_verification_record(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")
        asset_cls = _get_model("EnergyAsset")
        verif_cls = _get_model("VerificationRecord")

        user = user_cls(
            email=f"verif_user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Verified Prosumer",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        site = site_cls(owner_user_id=user.id, name="Solar Home", timezone="Asia/Kolkata")
        db_session.add(site)
        db_session.flush()

        asset = asset_cls(site_id=site.id, asset_type="pv", capacity_kw=8.0, status="active")
        db_session.add(asset)
        db_session.flush()

        now = datetime.now(UTC)
        record = verif_cls(
            user_id=user.id,
            asset_id=asset.id,
            verification_type="utility_account",
            source="discom",
            verification_level="document_verified",
            status="verified",
            verified_at=now,
        )
        db_session.add(record)
        db_session.flush()

        persisted = db_session.query(verif_cls).filter_by(id=record.id).one()
        assert persisted.user_id == user.id
        assert persisted.asset_id == asset.id
        assert persisted.verification_type == "utility_account"
        assert persisted.status == "verified"
        assert isinstance(persisted.id, uuid.UUID)


# ---------------------------------------------------------------------------
# 9. Consent Persistence
# ---------------------------------------------------------------------------


class TestConsentPersistence:
    """Verify persistence of the `consents` entity."""

    def test_consent_model_is_registered(self) -> None:
        cls = _get_model("Consent")
        assert cls.__tablename__ == "consents"

    def test_create_consent(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        consent_cls = _get_model("Consent")

        user = user_cls(
            email=f"consent_user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Consenting User",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        now = datetime.now(UTC)
        consent = consent_cls(
            user_id=user.id,
            scope="meter_data",
            granted_at=now,
        )
        db_session.add(consent)
        db_session.flush()

        persisted = db_session.query(consent_cls).filter_by(id=consent.id).one()
        assert persisted.user_id == user.id
        assert persisted.scope == "meter_data"
        assert persisted.granted_at is not None
        assert persisted.revoked_at is None
        assert isinstance(persisted.id, uuid.UUID)
