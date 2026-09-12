"""Phase 1 relationship & foreign key integrity tests.

Verifies the relationships, foreign keys, and integrity rules from docs/04_DATA_MODEL.md:
  1. Hierarchy: User -> Site -> Meter -> EnergyAsset -> InverterDevice
  2. GridNode hierarchy and Site association
  3. User -> UtilityAccount, VerificationRecord, Consent associations
  4. Invalid foreign key rejection (IntegrityError)
  5. Cascades and deletion behavior
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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


class TestEntityHierarchyRelationships:
    """Verify full User -> Site -> Meter / Asset -> Inverter hierarchy."""

    def test_full_prosumer_hierarchy_persistence_and_navigation(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        node_cls = _get_model("GridNode")
        site_cls = _get_model("Site")
        meter_cls = _get_model("Meter")
        asset_cls = _get_model("EnergyAsset")
        inv_cls = _get_model("InverterDevice")
        util_cls = _get_model("UtilityAccount")
        verif_cls = _get_model("VerificationRecord")
        consent_cls = _get_model("Consent")

        # 1. User
        user = user_cls(
            email=f"prosumer_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Ramesh Prosumer",
            role="prosumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        # 2. Utility Account
        now = datetime.now(timezone.utc)
        util_acc = util_cls(
            user_id=user.id,
            discom_code="BESCOM",
            consumer_number_hash="hash_123456",
            verification_level="discom_verified",
            verified_at=now,
        )
        db_session.add(util_acc)

        # 3. Grid Node (parent and child)
        feeder_node = node_cls(
            external_ref=f"FEEDER_{uuid.uuid4().hex[:8]}",
            node_type="feeder",
            nominal_voltage_kv=11.0,
        )
        db_session.add(feeder_node)
        db_session.flush()

        tx_node = node_cls(
            external_ref=f"TX_{uuid.uuid4().hex[:8]}",
            node_type="transformer",
            nominal_voltage_kv=0.415,
            parent_node_id=feeder_node.id,
            feeder_id="FEEDER_NORTH",
        )
        db_session.add(tx_node)
        db_session.flush()

        # 4. Site
        site = site_cls(
            owner_user_id=user.id,
            name="Ramesh Solar Villa",
            latitude=12.9352,
            longitude=77.6245,
            grid_node_id=tx_node.id,
            timezone="Asia/Kolkata",
        )
        db_session.add(site)
        db_session.flush()

        # 5. Meter
        meter = meter_cls(
            site_id=site.id,
            meter_type="net_meter",
            vendor="Secure Meters",
            external_meter_ref=f"SEC_{uuid.uuid4().hex[:8]}",
            verification_level="level_2",
            active=True,
        )
        db_session.add(meter)

        # 6. Energy Asset
        asset = asset_cls(
            site_id=site.id,
            asset_type="pv",
            capacity_kw=7.5,
            commissioned_at=now,
            status="active",
        )
        db_session.add(asset)
        db_session.flush()

        # 7. Inverter
        inverter = inv_cls(
            energy_asset_id=asset.id,
            manufacturer="Fronius",
            model="Primo 6.0-1",
            protocol="sunspec_modbus",
            external_device_ref=f"FRONIUS_{uuid.uuid4().hex[:8]}",
            adapter_type="sunspec_modbus",
        )
        db_session.add(inverter)

        # 8. Verification Record
        verif = verif_cls(
            user_id=user.id,
            asset_id=asset.id,
            verification_type="discom_bill",
            source="discom_api",
            verification_level="level_2",
            status="verified",
            verified_at=now,
        )
        db_session.add(verif)

        # 9. Consent
        consent = consent_cls(
            user_id=user.id,
            scope="telemetry_sharing",
            granted_at=now,
        )
        db_session.add(consent)
        db_session.flush()

        # Verify all objects are queryable with proper relations
        queried_site = db_session.query(site_cls).filter_by(id=site.id).one()
        assert queried_site.owner_user_id == user.id
        assert queried_site.grid_node_id == tx_node.id

        queried_meter = db_session.query(meter_cls).filter_by(site_id=site.id).one()
        assert queried_meter.id == meter.id

        queried_asset = db_session.query(asset_cls).filter_by(site_id=site.id).one()
        assert queried_asset.id == asset.id

        queried_inv = db_session.query(inv_cls).filter_by(energy_asset_id=asset.id).one()
        assert queried_inv.id == inverter.id


class TestInvalidForeignKeysFail:
    """Verify that database foreign key constraints reject dangling references."""

    def test_site_invalid_owner_fails(self, db_session: Session) -> None:
        site_cls = _get_model("Site")
        bad_site = site_cls(
            owner_user_id=uuid.uuid4(),  # Non-existent user
            name="Ghost Site",
            timezone="Asia/Kolkata",
        )
        db_session.add(bad_site)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_site_invalid_grid_node_fails(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")

        user = user_cls(
            email=f"valid_user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Valid User",
            role="consumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        bad_site = site_cls(
            owner_user_id=user.id,
            name="Bad Grid Site",
            grid_node_id=uuid.uuid4(),  # Non-existent node
            timezone="Asia/Kolkata",
        )
        db_session.add(bad_site)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_meter_invalid_site_fails(self, db_session: Session) -> None:
        meter_cls = _get_model("Meter")
        bad_meter = meter_cls(
            site_id=uuid.uuid4(),  # Non-existent site
            meter_type="smart_meter",
            vendor="L&T",
            external_meter_ref=f"MTR_{uuid.uuid4().hex[:8]}",
            active=True,
        )
        db_session.add(bad_meter)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_energy_asset_invalid_site_fails(self, db_session: Session) -> None:
        asset_cls = _get_model("EnergyAsset")
        bad_asset = asset_cls(
            site_id=uuid.uuid4(),  # Non-existent site
            asset_type="pv",
            capacity_kw=10.0,
            status="active",
        )
        db_session.add(bad_asset)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_inverter_invalid_asset_fails(self, db_session: Session) -> None:
        inv_cls = _get_model("InverterDevice")
        bad_inverter = inv_cls(
            energy_asset_id=uuid.uuid4(),  # Non-existent asset
            manufacturer="SMA",
            model="Sunny Boy",
            protocol="sunspec_modbus",
            external_device_ref=f"INV_{uuid.uuid4().hex[:8]}",
            adapter_type="simulator",
        )
        db_session.add(bad_inverter)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_utility_account_invalid_user_fails(self, db_session: Session) -> None:
        acc_cls = _get_model("UtilityAccount")
        bad_acc = acc_cls(
            user_id=uuid.uuid4(),  # Non-existent user
            discom_code="BESCOM",
            consumer_number_hash="hash_xyz",
            verification_level="unverified",
        )
        db_session.add(bad_acc)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_verification_record_invalid_user_fails(self, db_session: Session) -> None:
        verif_cls = _get_model("VerificationRecord")
        bad_verif = verif_cls(
            user_id=uuid.uuid4(),  # Non-existent user
            verification_type="government_id",
            source="manual",
            verification_level="level_1",
            status="pending",
        )
        db_session.add(bad_verif)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_consent_invalid_user_fails(self, db_session: Session) -> None:
        consent_cls = _get_model("Consent")
        now = datetime.now(timezone.utc)
        bad_consent = consent_cls(
            user_id=uuid.uuid4(),  # Non-existent user
            scope="p2p_trading",
            granted_at=now,
        )
        db_session.add(bad_consent)
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestDeletionAndUpdateBehavior:
    """Verify delete restrictions or cascades on parent entities."""

    def test_cannot_delete_user_with_active_sites(self, db_session: Session) -> None:
        user_cls = _get_model("User")
        site_cls = _get_model("Site")

        user = user_cls(
            email=f"del_user_{uuid.uuid4().hex[:8]}@example.com",
            display_name="Delete Candidate",
            role="consumer",
            status="active",
        )
        db_session.add(user)
        db_session.flush()

        site = site_cls(
            owner_user_id=user.id,
            name="Protected Site",
            timezone="Asia/Kolkata",
        )
        db_session.add(site)
        db_session.flush()

        # Attempt to delete the user while site still references it
        db_session.delete(user)
        with pytest.raises(IntegrityError):
            db_session.flush()
