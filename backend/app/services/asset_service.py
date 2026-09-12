"""Asset service for sites, meters, energy assets, inverters, and verification.

Coordinates database operations for physical and digital energy assets
(docs/03_REPOSITORY_STRUCTURE.md, docs/05_API_SPEC.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models.assets import (
    EnergyAsset,
    InverterDevice,
    Meter,
    Site,
    VerificationRecord,
)
from app.db.models.grid import GridNode
from app.db.models.identity import User
from app.schemas.assets import (
    EnergyAssetCreate,
    InverterCreate,
    MeterCreate,
    SiteCreate,
    VerificationCreate,
)


def create_site(db: Session, payload: SiteCreate) -> Site:
    """Register a new physical site/facility."""
    user = db.get(User, payload.owner_user_id)
    if not user:
        raise NotFoundError(
            f"Owner user with id '{payload.owner_user_id}' was not found.",
            details={"owner_user_id": str(payload.owner_user_id)},
        )

    if payload.grid_node_id:
        grid_node = db.get(GridNode, payload.grid_node_id)
        if not grid_node:
            raise NotFoundError(
                f"Grid node with id '{payload.grid_node_id}' was not found.",
                details={"grid_node_id": str(payload.grid_node_id)},
            )

    site = Site(
        owner_user_id=payload.owner_user_id,
        name=payload.name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        grid_node_id=payload.grid_node_id,
        timezone=payload.timezone,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


def get_site(db: Session, site_id: uuid.UUID) -> Site:
    """Retrieve site by ID or raise NotFoundError."""
    site = db.get(Site, site_id)
    if not site:
        raise NotFoundError(
            f"Site with id '{site_id}' was not found.",
            details={"site_id": str(site_id)},
        )
    return site


def create_meter(db: Session, site_id: uuid.UUID, payload: MeterCreate) -> Meter:
    """Attach a meter to an existing site."""
    # Ensure site exists
    get_site(db, site_id)

    meter = Meter(
        site_id=site_id,
        meter_type=payload.meter_type.value,
        vendor=payload.vendor,
        external_meter_ref=payload.external_meter_ref,
        verification_level=payload.verification_level.value,
        active=payload.active,
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def create_energy_asset(
    db: Session, site_id: uuid.UUID, payload: EnergyAssetCreate
) -> EnergyAsset:
    """Register an energy asset (PV, battery, EV) under a site."""
    # Ensure site exists
    get_site(db, site_id)

    asset = EnergyAsset(
        site_id=site_id,
        asset_type=payload.asset_type.value,
        capacity_kw=payload.capacity_kw,
        commissioned_at=payload.commissioned_at,
        status=payload.status.value,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def get_energy_asset(db: Session, asset_id: uuid.UUID) -> EnergyAsset:
    """Retrieve an energy asset by ID or raise NotFoundError."""
    asset = db.get(EnergyAsset, asset_id)
    if not asset:
        raise NotFoundError(
            f"Energy asset with id '{asset_id}' was not found.",
            details={"asset_id": str(asset_id)},
        )
    return asset


def create_verification(
    db: Session, asset_id: uuid.UUID, payload: VerificationCreate
) -> VerificationRecord:
    """Submit a verification record for an energy asset."""
    asset = get_energy_asset(db, asset_id)

    verified_at = payload.verified_at
    if verified_at is None and payload.status.value == "approved":
        verified_at = datetime.now(UTC)

    # Resolve user_id from owner of the site
    owner_user_id = asset.site.owner_user_id if asset.site else None

    verification = VerificationRecord(
        asset_id=asset.id,
        user_id=owner_user_id,
        verification_type=payload.verification_type.value,
        source=payload.source,
        verification_level=payload.verification_level.value,
        status=payload.status.value,
        verified_at=verified_at,
        expires_at=payload.expires_at,
    )

    # If verification is approved, activate the asset
    if payload.status.value == "approved":
        asset.status = "active"

    db.add(verification)
    db.commit()
    db.refresh(verification)
    return verification


def get_asset_verification(
    db: Session, asset_id: uuid.UUID
) -> VerificationRecord:
    """Get the latest verification status for an energy asset."""
    get_energy_asset(db, asset_id)

    record = db.execute(
        select(VerificationRecord)
        .where(VerificationRecord.asset_id == asset_id)
        .order_by(desc(VerificationRecord.verified_at), desc(VerificationRecord.id))
    ).scalars().first()

    if not record:
        raise NotFoundError(
            f"No verification record found for asset '{asset_id}'.",
            details={"asset_id": str(asset_id)},
        )
    return record


def create_inverter(db: Session, payload: InverterCreate) -> InverterDevice:
    """Register inverter device metadata and adapter type."""
    # Ensure associated energy asset exists
    get_energy_asset(db, payload.energy_asset_id)

    inverter = InverterDevice(
        energy_asset_id=payload.energy_asset_id,
        manufacturer=payload.manufacturer,
        model=payload.model,
        protocol=payload.protocol.value if payload.protocol else None,
        external_device_ref=payload.external_device_ref,
        adapter_type=payload.adapter_type,
    )
    db.add(inverter)
    db.commit()
    db.refresh(inverter)
    return inverter
