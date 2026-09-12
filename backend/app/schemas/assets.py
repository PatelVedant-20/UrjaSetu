"""API contracts for the Assets / Verification resource group (docs/05_API_SPEC.md).

Transport-layer models only. Field names, units and enum values come from
docs/04_DATA_MODEL.md — kW for capacity, UUIDs for identifiers, UTC timestamps.
Enums are imported from `app.domain.enums`, never redeclared.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    EnergyAssetStatus,
    EnergyAssetType,
    InverterProtocol,
    MeterType,
    VerificationLevel,
    VerificationSource,
    VerificationStatus,
    VerificationType,
)

# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------


class SiteCreate(BaseModel):
    """`POST /sites` request."""

    owner_user_id: UUID
    name: str = Field(..., min_length=1, max_length=200)
    # Approximate/demo-safe coordinates (docs/04_DATA_MODEL.md entity 3).
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    # Optional: a site is registered before it is mapped onto the digital twin.
    grid_node_id: UUID | None = None
    timezone: str = Field(default="Asia/Kolkata", max_length=64)


class SiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    name: str
    latitude: Decimal | None
    longitude: Decimal | None
    grid_node_id: UUID | None
    timezone: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Meters
# ---------------------------------------------------------------------------


class MeterCreate(BaseModel):
    """`POST /sites/{site_id}/meters` request.

    `site_id` comes from the path, not the body, so the two cannot disagree.
    """

    meter_type: MeterType
    vendor: str | None = Field(default=None, max_length=128)
    external_meter_ref: str | None = Field(default=None, max_length=128)
    verification_level: VerificationLevel = VerificationLevel.NONE
    active: bool = True


class MeterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: UUID
    meter_type: MeterType
    vendor: str | None
    external_meter_ref: str | None
    verification_level: VerificationLevel
    active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Energy assets
# ---------------------------------------------------------------------------


class EnergyAssetCreate(BaseModel):
    """`POST /sites/{site_id}/energy-assets` request."""

    asset_type: EnergyAssetType
    # kW (docs/00_PROJECT_BIBLE.md section 6). Decimal, not float: this value
    # feeds settlement arithmetic in later phases.
    capacity_kw: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    commissioned_at: datetime | None = None
    status: EnergyAssetStatus = EnergyAssetStatus.PLANNED


class EnergyAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    site_id: UUID
    asset_type: EnergyAssetType
    capacity_kw: Decimal
    commissioned_at: datetime | None
    status: EnergyAssetStatus
    created_at: datetime
    updated_at: datetime


class SiteDetail(SiteRead):
    """`GET /sites/{site_id}` response — the site and what is installed on it."""

    meters: list[MeterRead] = Field(default_factory=list)
    energy_assets: list[EnergyAssetRead] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Inverters
# ---------------------------------------------------------------------------


class InverterCreate(BaseModel):
    """`POST /inverters` request — device metadata and adapter type.

    Metadata only. Registering an inverter opens no connection and loads no
    protocol library; `adapter_type` names an implementation under
    `app/adapters/inverter/` for a later phase to resolve.
    """

    energy_asset_id: UUID
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    protocol: InverterProtocol = InverterProtocol.UNKNOWN
    external_device_ref: str | None = Field(default=None, max_length=128)
    adapter_type: str | None = Field(default=None, max_length=64)


class InverterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    energy_asset_id: UUID
    manufacturer: str | None
    model: str | None
    protocol: InverterProtocol
    external_device_ref: str | None
    adapter_type: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class VerificationCreate(BaseModel):
    """`POST /assets/{asset_id}/verification` request.

    `verification_type` states what the evidence attests. docs/04_DATA_MODEL.md
    entity 8 keeps identity, utility-account, meter and asset evidence in one
    table, so this endpoint carries all of them; the asset from the path is
    recorded as the record's scope.
    """

    verification_type: VerificationType
    source: VerificationSource
    verification_level: VerificationLevel = VerificationLevel.NONE
    status: VerificationStatus = VerificationStatus.PENDING
    verified_at: datetime | None = None
    expires_at: datetime | None = None


class VerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    asset_id: UUID | None
    verification_type: VerificationType
    source: VerificationSource
    verification_level: VerificationLevel
    status: VerificationStatus
    verified_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
