"""Repositories for the asset registry module."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models.assets import (
    EnergyAsset,
    GridNode,
    InverterDevice,
    Meter,
    Site,
    VerificationRecord,
)
from app.domain.enums import EnergyAssetType, VerificationStatus, VerificationType
from app.repositories.base import BaseRepository


class GridNodeRepository(BaseRepository[GridNode]):
    model = GridNode

    def get_by_external_ref(self, external_ref: str) -> GridNode | None:
        stmt = select(GridNode).where(GridNode.external_ref == external_ref)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_children(self, parent_node_id: UUID) -> Sequence[GridNode]:
        stmt = select(GridNode).where(GridNode.parent_node_id == parent_node_id)
        return self.session.execute(stmt).scalars().all()

    def list_by_feeder(self, feeder_id: str) -> Sequence[GridNode]:
        stmt = select(GridNode).where(GridNode.feeder_id == feeder_id)
        return self.session.execute(stmt).scalars().all()


class SiteRepository(BaseRepository[Site]):
    model = Site

    def list_for_owner(self, owner_user_id: UUID) -> Sequence[Site]:
        stmt = select(Site).where(Site.owner_user_id == owner_user_id)
        return self.session.execute(stmt).scalars().all()

    def get_with_registry(self, site_id: UUID) -> Site | None:
        """Load a site together with its meters, assets and inverters.

        Eager-loaded in one round trip: the registry view of a site always
        needs all three, and lazy loading them turns one query into N.
        """
        stmt = (
            select(Site)
            .where(Site.id == site_id)
            .options(
                selectinload(Site.meters),
                selectinload(Site.energy_assets).selectinload(EnergyAsset.inverters),
            )
        )
        return self.session.execute(stmt).scalar_one_or_none()


class MeterRepository(BaseRepository[Meter]):
    model = Meter

    def list_for_site(self, site_id: UUID) -> Sequence[Meter]:
        stmt = select(Meter).where(Meter.site_id == site_id)
        return self.session.execute(stmt).scalars().all()

    def get_by_external_ref(self, external_meter_ref: str) -> Meter | None:
        stmt = select(Meter).where(Meter.external_meter_ref == external_meter_ref)
        return self.session.execute(stmt).scalar_one_or_none()


class EnergyAssetRepository(BaseRepository[EnergyAsset]):
    model = EnergyAsset

    def list_for_site(
        self, site_id: UUID, *, asset_type: EnergyAssetType | None = None
    ) -> Sequence[EnergyAsset]:
        stmt = select(EnergyAsset).where(EnergyAsset.site_id == site_id)
        if asset_type is not None:
            stmt = stmt.where(EnergyAsset.asset_type == asset_type)
        return self.session.execute(stmt).scalars().all()

    def list_for_owner(self, owner_user_id: UUID) -> Sequence[EnergyAsset]:
        stmt = select(EnergyAsset).join(Site).where(Site.owner_user_id == owner_user_id)
        return self.session.execute(stmt).scalars().all()


class InverterDeviceRepository(BaseRepository[InverterDevice]):
    model = InverterDevice

    def list_for_asset(self, energy_asset_id: UUID) -> Sequence[InverterDevice]:
        stmt = select(InverterDevice).where(InverterDevice.energy_asset_id == energy_asset_id)
        return self.session.execute(stmt).scalars().all()

    def get_by_external_ref(self, external_device_ref: str) -> InverterDevice | None:
        stmt = select(InverterDevice).where(
            InverterDevice.external_device_ref == external_device_ref
        )
        return self.session.execute(stmt).scalar_one_or_none()


class VerificationRecordRepository(BaseRepository[VerificationRecord]):
    model = VerificationRecord

    def list_for_user(self, user_id: UUID) -> Sequence[VerificationRecord]:
        stmt = select(VerificationRecord).where(VerificationRecord.user_id == user_id)
        return self.session.execute(stmt).scalars().all()

    def list_for_asset(self, asset_id: UUID) -> Sequence[VerificationRecord]:
        stmt = select(VerificationRecord).where(VerificationRecord.asset_id == asset_id)
        return self.session.execute(stmt).scalars().all()

    def list_verified_for_user(
        self, user_id: UUID, *, verification_type: VerificationType | None = None
    ) -> Sequence[VerificationRecord]:
        """Records currently in the VERIFIED state.

        Expiry is not evaluated here — a record can be VERIFIED with an
        `expires_at` already in the past. Deciding what that means is policy,
        and lives in `app.domain.policies.eligibility`.
        """
        stmt = select(VerificationRecord).where(
            VerificationRecord.user_id == user_id,
            VerificationRecord.status == VerificationStatus.VERIFIED,
        )
        if verification_type is not None:
            stmt = stmt.where(VerificationRecord.verification_type == verification_type)
        return self.session.execute(stmt).scalars().all()
