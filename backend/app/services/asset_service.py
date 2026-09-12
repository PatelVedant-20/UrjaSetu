"""Asset service for sites, meters, energy assets, inverters, and verification.

Coordinates database operations for physical and digital energy assets
(docs/03_REPOSITORY_STRUCTURE.md, docs/05_API_SPEC.md).
"""Asset registry service — sites, meters, energy assets, inverters, verification.

Owns the transaction boundary for registry writes. Every operation validates
that the parent resource exists before writing, so a bad reference returns a
404 naming the missing parent rather than a raw foreign-key error.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models.assets import (
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    EnergyAsset,
    InverterDevice,
    Meter,
    Site,
    VerificationRecord,
)
from app.db.models.grid import GridNode
from app.db.models.identity import User
from app.repositories import (
    EnergyAssetRepository,
    GridNodeRepository,
    InverterDeviceRepository,
    MeterRepository,
    SiteRepository,
    UserRepository,
    VerificationRecordRepository,
)
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
from app.services import ResourceConflictError, ResourceNotFoundError

# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------


def create_site(session: Session, payload: SiteCreate) -> Site:
    """Register a site for an existing owner, optionally mapped to a grid node."""
    if UserRepository(session).get(payload.owner_user_id) is None:
        raise ResourceNotFoundError("user", payload.owner_user_id)

    if payload.grid_node_id is not None and (
        GridNodeRepository(session).get(payload.grid_node_id) is None
    ):
        raise ResourceNotFoundError("grid_node", payload.grid_node_id)

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
    SiteRepository(session).add(site)
    session.commit()
    session.refresh(site)
    return site


def get_site(session: Session, site_id: UUID) -> Site:
    site = SiteRepository(session).get(site_id)
    if site is None:
        raise ResourceNotFoundError("site", site_id)
    return site


def get_site_detail(session: Session, site_id: UUID) -> Site:
    """A site with its meters, assets and inverters loaded in one round trip."""
    site = SiteRepository(session).get_with_registry(site_id)
    if site is None:
        raise ResourceNotFoundError("site", site_id)
    return site


# ---------------------------------------------------------------------------
# Meters
# ---------------------------------------------------------------------------


def attach_meter(session: Session, site_id: UUID, payload: MeterCreate) -> Meter:
    """Attach a meter to a site.

    `external_meter_ref` is globally unique: two sites claiming the same
    physical meter would double-count energy at reconciliation, so the conflict
    is reported rather than allowed.
    """
    get_site(session, site_id)

    meter = Meter(
        site_id=site_id,
        meter_type=payload.meter_type,
        vendor=payload.vendor,
        external_meter_ref=payload.external_meter_ref,
        verification_level=payload.verification_level,
        active=payload.active,
    )
    try:
        MeterRepository(session).add(meter)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ResourceConflictError(
            "A meter with this external reference is already registered.",
            code="METER_REF_ALREADY_REGISTERED",
            details={"external_meter_ref": payload.external_meter_ref},
        ) from exc

    session.refresh(meter)
    return meter


# ---------------------------------------------------------------------------
# Energy assets
# ---------------------------------------------------------------------------


def register_energy_asset(
    session: Session, site_id: UUID, payload: EnergyAssetCreate
) -> EnergyAsset:
    """Register a generation or flexible-energy asset on a site."""
    get_site(session, site_id)

    asset = EnergyAsset(
        site_id=site_id,
        asset_type=payload.asset_type,
        capacity_kw=payload.capacity_kw,
        commissioned_at=payload.commissioned_at,
        status=payload.status,
    )
    EnergyAssetRepository(session).add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def get_energy_asset(session: Session, asset_id: UUID) -> EnergyAsset:
    asset = EnergyAssetRepository(session).get(asset_id)
    if asset is None:
        raise ResourceNotFoundError("energy_asset", asset_id)
    return asset


# ---------------------------------------------------------------------------
# Inverters
# ---------------------------------------------------------------------------


def register_inverter(session: Session, payload: InverterCreate) -> InverterDevice:
    """Record inverter metadata against an energy asset.

    Metadata only: no connection is opened and no protocol library is loaded.
    """
    get_energy_asset(session, payload.energy_asset_id)

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
        protocol=payload.protocol,
        external_device_ref=payload.external_device_ref,
        adapter_type=payload.adapter_type,
    )
    try:
        InverterDeviceRepository(session).add(inverter)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ResourceConflictError(
            "An inverter with this external reference is already registered.",
            code="INVERTER_REF_ALREADY_REGISTERED",
            details={"external_device_ref": payload.external_device_ref},
        ) from exc

    session.refresh(inverter)
    return inverter


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def submit_asset_verification(
    session: Session, asset_id: UUID, payload: VerificationCreate
) -> VerificationRecord:
    """Record verification evidence scoped to an energy asset.

    The owning user is derived from the asset's site rather than taken from the
    request, so a record cannot be filed against someone else's identity.
    """
    asset = get_energy_asset(session, asset_id)
    owner_user_id = get_site(session, asset.site_id).owner_user_id

    record = VerificationRecord(
        user_id=owner_user_id,
        asset_id=asset_id,
        verification_type=payload.verification_type,
        source=payload.source,
        verification_level=payload.verification_level,
        status=payload.status,
        verified_at=payload.verified_at,
        expires_at=payload.expires_at,
    )
    try:
        VerificationRecordRepository(session).add(record)
        session.commit()
    except IntegrityError as exc:
        # The table's check constraints reject inconsistent evidence, e.g.
        # status VERIFIED with no verified_at, or expiry before verification.
        session.rollback()
        raise ResourceConflictError(
            "The verification record is inconsistent and was rejected.",
            code="VERIFICATION_RECORD_INVALID",
        ) from exc

    session.refresh(record)
    return record


def list_asset_verifications(session: Session, asset_id: UUID) -> Sequence[VerificationRecord]:
    """Verification status for an asset."""
    get_energy_asset(session, asset_id)
    return VerificationRecordRepository(session).list_for_asset(asset_id)
