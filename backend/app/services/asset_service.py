"""Asset registry service — sites, meters, energy assets, inverters, verification.

Owns the transaction boundary for registry writes. Every operation validates
that the parent resource exists before writing, so a bad reference returns a
404 naming the missing parent rather than a raw foreign-key error.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    EnergyAsset,
    InverterDevice,
    Meter,
    Site,
    VerificationRecord,
)
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

# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------


def create_site(session: Session, payload: SiteCreate) -> Site:
    """Register a site for an existing owner, optionally mapped to a grid node."""
    if UserRepository(session).get(payload.owner_user_id) is None:
        raise NotFoundError(
            "User not found.",
            code="USER_NOT_FOUND",
            details={"id": str(payload.owner_user_id)},
        )

    if payload.grid_node_id is not None and (
        GridNodeRepository(session).get(payload.grid_node_id) is None
    ):
        raise NotFoundError(
            "Grid node not found.",
            code="GRID_NODE_NOT_FOUND",
            details={"id": str(payload.grid_node_id)},
        )

    site = Site(
        owner_user_id=payload.owner_user_id,
        name=payload.name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        grid_node_id=payload.grid_node_id,
        timezone=payload.timezone,
    )
    SiteRepository(session).add(site)
    session.commit()
    session.refresh(site)
    return site


def get_site(session: Session, site_id: UUID) -> Site:
    site = SiteRepository(session).get(site_id)
    if site is None:
        raise NotFoundError("Site not found.", code="SITE_NOT_FOUND", details={"id": str(site_id)})
    return site


def get_site_detail(session: Session, site_id: UUID) -> Site:
    """A site with its meters, assets and inverters loaded in one round trip."""
    site = SiteRepository(session).get_with_registry(site_id)
    if site is None:
        raise NotFoundError("Site not found.", code="SITE_NOT_FOUND", details={"id": str(site_id)})
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
        raise ConflictError(
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
        raise NotFoundError(
            "Energy asset not found.",
            code="ENERGY_ASSET_NOT_FOUND",
            details={"id": str(asset_id)},
        )
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
        protocol=payload.protocol,
        external_device_ref=payload.external_device_ref,
        adapter_type=payload.adapter_type,
    )
    try:
        InverterDeviceRepository(session).add(inverter)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
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
        raise ConflictError(
            "The verification record is inconsistent and was rejected.",
            code="VERIFICATION_RECORD_INVALID",
        ) from exc

    session.refresh(record)
    return record


def list_asset_verifications(session: Session, asset_id: UUID) -> Sequence[VerificationRecord]:
    """Verification status for an asset."""
    get_energy_asset(session, asset_id)
    return VerificationRecordRepository(session).list_for_asset(asset_id)
