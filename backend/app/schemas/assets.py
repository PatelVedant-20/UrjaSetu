"""Asset domain Pydantic schemas.

Transport-layer DTOs only. No persistence logic here
(docs/03_REPOSITORY_STRUCTURE.md ownership rules).
Covers sites, meters, energy assets, inverter devices, and verification records
(docs/04_DATA_MODEL.md sections 3, 5, 6, 7, 8).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.users import VerificationLevel

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MeterType(str, Enum):
    smart = "smart"
    net = "net"
    gross = "gross"


class AssetType(str, Enum):
    pv = "pv"
    battery = "battery"
    ev = "ev"
    other = "other"


class AssetStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    pending_verification = "pending_verification"
    decommissioned = "decommissioned"


class InverterProtocol(str, Enum):
    sunspec = "sunspec"
    modbus = "modbus"
    proprietary = "proprietary"


class VerificationType(str, Enum):
    kyc = "kyc"
    asset_registration = "asset_registration"
    meter_certification = "meter_certification"


class VerificationStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


# ---------------------------------------------------------------------------
# Site schemas
# ---------------------------------------------------------------------------


class SiteCreate(BaseModel):
    """POST /api/v1/sites request body."""

    owner_user_id: uuid.UUID = Field(
        ...,
        description="ID of the platform user who owns this physical site.",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable site/building/facility name.",
        examples=["Gokuldham Solar Rooftop A"],
    )
    latitude: float | None = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Demo-safe latitude coordinate (approximate).",
        examples=[19.0760],
    )
    longitude: float | None = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Demo-safe longitude coordinate (approximate).",
        examples=[72.8777],
    )
    grid_node_id: uuid.UUID | None = Field(
        default=None,
        description="Optional foreign key to a grid digital-twin node.",
    )
    timezone: str = Field(
        default="Asia/Kolkata",
        max_length=64,
        description="IANA timezone identifier for local time conversion.",
        examples=["Asia/Kolkata"],
    )


class SiteResponse(BaseModel):
    """Site resource representation."""

    id: uuid.UUID
    owner_user_id: uuid.UUID
    name: str
    latitude: float | None
    longitude: float | None
    grid_node_id: uuid.UUID | None
    timezone: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Meter schemas
# ---------------------------------------------------------------------------


class MeterCreate(BaseModel):
    """POST /api/v1/sites/{site_id}/meters request body."""

    meter_type: MeterType = Field(
        default=MeterType.net,
        description="Type of meter: smart, net, or gross.",
    )
    vendor: str | None = Field(
        default=None,
        max_length=128,
        description="Meter vendor/manufacturer.",
        examples=["Schneider Electric"],
    )
    external_meter_ref: str | None = Field(
        default=None,
        max_length=128,
        description="DISCOM or hardware serial identifier.",
        examples=["MTR-2026-9871"],
    )
    verification_level: VerificationLevel = Field(
        default=VerificationLevel.none,
        description="Initial verification level of the meter.",
    )
    active: bool = Field(
        default=True,
        description="Whether the meter is currently active for measurement.",
    )


class MeterResponse(BaseModel):
    """Meter resource representation."""

    id: uuid.UUID
    site_id: uuid.UUID
    meter_type: MeterType
    vendor: str | None
    external_meter_ref: str | None
    verification_level: VerificationLevel
    active: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Energy Asset schemas
# ---------------------------------------------------------------------------


class EnergyAssetCreate(BaseModel):
    """POST /api/v1/sites/{site_id}/energy-assets request body."""

    asset_type: AssetType = Field(
        default=AssetType.pv,
        description="Type of asset: pv, battery, ev, other.",
    )
    capacity_kw: float = Field(
        ...,
        gt=0.0,
        description="Nameplate rated capacity in kilowatts (kW).",
        examples=[10.5],
    )
    commissioned_at: datetime | None = Field(
        default=None,
        description="ISO-8601 UTC timestamp when asset was commissioned.",
    )
    status: AssetStatus = Field(
        default=AssetStatus.pending_verification,
        description="Initial asset operational status.",
    )


class EnergyAssetResponse(BaseModel):
    """Energy asset resource representation."""

    id: uuid.UUID
    site_id: uuid.UUID
    asset_type: AssetType
    capacity_kw: float
    commissioned_at: datetime | None
    status: AssetStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Inverter Device schemas
# ---------------------------------------------------------------------------


class InverterCreate(BaseModel):
    """POST /api/v1/inverters request body."""

    energy_asset_id: uuid.UUID = Field(
        ...,
        description="Foreign key to the associated EnergyAsset.",
    )
    manufacturer: str | None = Field(
        default=None,
        max_length=128,
        examples=["SMA Solar"],
    )
    model: str | None = Field(
        default=None,
        max_length=128,
        examples=["Sunny Tripower 10.0"],
    )
    protocol: InverterProtocol | None = Field(
        default=None,
        description="Communication protocol: sunspec, modbus, or proprietary.",
    )
    external_device_ref: str | None = Field(
        default=None,
        max_length=128,
        examples=["INV-SN-882103"],
    )
    adapter_type: str | None = Field(
        default=None,
        max_length=64,
        description="Registered adapter identifier in app/adapters/inverter/.",
        examples=["sma_sunspec"],
    )


class InverterResponse(BaseModel):
    """Inverter device resource representation."""

    id: uuid.UUID
    energy_asset_id: uuid.UUID
    manufacturer: str | None
    model: str | None
    protocol: InverterProtocol | None
    external_device_ref: str | None
    adapter_type: str | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Verification Record schemas
# ---------------------------------------------------------------------------


class VerificationCreate(BaseModel):
    """POST /api/v1/assets/{asset_id}/verification request body."""

    verification_type: VerificationType = Field(
        default=VerificationType.asset_registration,
        description="Type of verification: kyc, asset_registration, meter_certification.",
    )
    source: str | None = Field(
        default=None,
        max_length=128,
        description="Origin of verification evidence (e.g. DISCOM portal, physical inspection).",
        examples=["DISCOM_INSPECTOR"],
    )
    verification_level: VerificationLevel = Field(
        default=VerificationLevel.basic,
        description="Verification level attained.",
    )
    status: VerificationStatus = Field(
        default=VerificationStatus.approved,
        description="Status of this verification record.",
    )
    verified_at: datetime | None = Field(
        default=None,
        description="When verification was performed. Defaults to now if approved.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Optional expiration timestamp for periodic renewal.",
    )


class VerificationResponse(BaseModel):
    """Verification record resource representation."""

    id: uuid.UUID
    user_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    verification_type: VerificationType
    source: str | None
    verification_level: VerificationLevel
    status: VerificationStatus
    verified_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}
