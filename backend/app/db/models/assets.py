"""Asset domain persistence models.

Covers sites, meters, energy assets, inverter devices and verification records
(docs/04_DATA_MODEL.md sections 3, 5, 6, 7, 8).

All Phase-1 asset tables. No telemetry, market or settlement columns here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.grid import GridNode
    from app.db.models.identity import User


class Site(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Physical/community location entity (docs/04_DATA_MODEL.md section 3).

    Coordinates are approximate/demo-safe — never exact GPS from real meters.
    `timezone` is an IANA timezone string (e.g. 'Asia/Kolkata').
    """

    __tablename__ = "sites"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(precision=9, scale=6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(precision=9, scale=6), nullable=True)
    grid_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("grid_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")

    owner: Mapped[User] = relationship(  # noqa: F821
        "User", back_populates="sites"
    )
    meters: Mapped[list[Meter]] = relationship(
        "Meter", back_populates="site", cascade="all, delete-orphan"
    )
    energy_assets: Mapped[list[EnergyAsset]] = relationship(
        "EnergyAsset", back_populates="site", cascade="all, delete-orphan"
    )
    grid_node: Mapped[GridNode | None] = relationship("GridNode")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Site id={self.id} name={self.name!r}>"


class Meter(UUIDPrimaryKeyMixin, Base):
    """Smart/net meter representation (docs/04_DATA_MODEL.md section 5).

    `meter_type` values: smart | net | gross
    `verification_level` values: none | basic | kyc | verified
    """

    __tablename__ = "meters"

    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meter_type: Mapped[str] = mapped_column(String(32), nullable=False, default="net")
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    external_meter_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    verification_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none"
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    site: Mapped[Site] = relationship("Site", back_populates="meters")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Meter id={self.id} type={self.meter_type!r} active={self.active}>"


class EnergyAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Generation or flexible-energy asset (docs/04_DATA_MODEL.md section 6).

    `asset_type` values: pv | battery | ev | other (pv is the Phase-1 focus)
    `status` values: active | inactive | pending_verification | decommissioned
    """

    __tablename__ = "energy_assets"

    site_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="pv")
    capacity_kw: Mapped[float] = mapped_column(Numeric(precision=10, scale=3), nullable=False)
    commissioned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_verification"
    )

    site: Mapped[Site] = relationship("Site", back_populates="energy_assets")
    inverter_devices: Mapped[list[InverterDevice]] = relationship(
        "InverterDevice", back_populates="energy_asset", cascade="all, delete-orphan"
    )
    verification_records: Mapped[list[VerificationRecord]] = relationship(
        "VerificationRecord",
        primaryjoin="EnergyAsset.id == foreign(VerificationRecord.asset_id)",
        back_populates="energy_asset",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EnergyAsset id={self.id} type={self.asset_type!r} kw={self.capacity_kw}>"


class InverterDevice(UUIDPrimaryKeyMixin, Base):
    """Device metadata for PV systems (docs/04_DATA_MODEL.md section 7).

    `protocol` values: sunspec | modbus | proprietary
    `adapter_type` links to the adapter registry in app/adapters/inverter/.
    """

    __tablename__ = "inverter_devices"

    energy_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("energy_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    protocol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_device_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    adapter_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    energy_asset: Mapped[EnergyAsset] = relationship(
        "EnergyAsset", back_populates="inverter_devices"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InverterDevice id={self.id} protocol={self.protocol!r}>"


class VerificationRecord(UUIDPrimaryKeyMixin, Base):
    """Trust and eligibility evidence (docs/04_DATA_MODEL.md section 8).

    Either `user_id` OR `asset_id` (energy asset) is the primary subject,
    per the spec. Both nullable; application logic enforces that at least one
    is set (Pydantic validator on the schema, not DB constraint, to allow
    cross-entity verification records in future).

    `verification_type` values: kyc | asset_registration | meter_certification
    `status` values: pending | approved | rejected | expired
    `verification_level` values: none | basic | kyc | verified
    """

    __tablename__ = "verification_records"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("energy_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    energy_asset: Mapped[EnergyAsset | None] = relationship(
        "EnergyAsset",
        primaryjoin="VerificationRecord.asset_id == EnergyAsset.id",
        back_populates="verification_records",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VerificationRecord id={self.id} type={self.verification_type!r}>"
