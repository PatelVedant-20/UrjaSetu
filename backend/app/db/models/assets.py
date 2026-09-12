"""Asset registry persistence models.

`grid_nodes`, `sites`, `meters`, `energy_assets`, `inverter_devices` and
`verification_records` — the `assets` module of docs/01_FINAL_ARCHITECTURE.md,
entities 3-8 of docs/04_DATA_MODEL.md.

Persistence only. Nothing here imports Power Grid Model, pySunSpec2 or any
other external runtime: `grid_nodes.external_ref`, `inverter_devices.protocol`
and `inverter_devices.adapter_type` are the metadata that lets a future adapter
bind to a row without the domain knowing which library did it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.domain.enums import (
    EnergyAssetStatus,
    EnergyAssetType,
    GridNodeType,
    InverterProtocol,
    MeterType,
    VerificationLevel,
    VerificationSource,
    VerificationStatus,
    VerificationType,
)

if TYPE_CHECKING:
    from app.db.models.identity import User

# Site coordinates are demo-safe approximations (docs/04_DATA_MODEL.md entity 3),
# so six decimal places (~0.1 m) is already more precision than the data carries.
_COORD = Numeric(9, 6)


class GridNode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A node in the distribution digital twin (docs/04_DATA_MODEL.md entity 4).

    Self-referencing through `parent_node_id`, which models the radial topology
    of a distribution network: substation -> feeder -> transformer ->
    connection point.
    """

    __tablename__ = "grid_nodes"

    # Stable identifier of this node in the external network model. Unique so a
    # twin node maps to exactly one row; this is the handle a future Power Grid
    # Model adapter will resolve against.
    external_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[GridNodeType] = mapped_column(
        pg_enum(GridNodeType, "grid_node_type"), nullable=False
    )
    nominal_voltage_kv: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    parent_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grid_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # A plain grouping identifier, not a foreign key: docs/04_DATA_MODEL.md
    # marks its foreign keys explicitly ("user_id FK users") and does not mark
    # this one, and `grid_snapshots.feeder_id` (entity 16) uses it the same way.
    feeder_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Continuous rating, in kW, of the element that connects this node to its
    # parent — the nameplate rating on a `transformer` node, the conductor's
    # thermal rating on any other. Without it, loading is a percentage of
    # nothing and no overload can be detected (Phase 5).
    #
    # It lives on the child rather than in a separate edge table because this
    # topology is radial: every node has at most one parent, so an edge and its
    # lower node are one-to-one, and `grid_nodes` stays the single source of
    # topology. A meshed network, or parallel circuits between the same pair of
    # nodes, would break that correspondence and is what would justify a
    # dedicated edge table later.
    #
    # NULL means the twin does not record a rating, which is not a rating of
    # zero: a validation that needs it concludes `unknown`, never `safe`.
    # A root node has no upstream element, so NULL is also simply correct there.
    rated_capacity_kw: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    parent: Mapped[GridNode | None] = relationship(
        back_populates="children",
        remote_side=lambda: [GridNode.id],
    )
    children: Mapped[list[GridNode]] = relationship(back_populates="parent")
    sites: Mapped[list[Site]] = relationship(back_populates="grid_node")

    __table_args__ = (
        UniqueConstraint("external_ref", name="uq_grid_nodes_external_ref"),
        CheckConstraint("nominal_voltage_kv > 0", name="nominal_voltage_positive"),
        # A zero-rated element would compute as infinite loading rather than as
        # the "unknown" that a missing rating actually means.
        CheckConstraint(
            "rated_capacity_kw IS NULL OR rated_capacity_kw > 0",
            name="rated_capacity_positive",
        ),
        # A node cannot be its own parent. Deeper cycles are a topology concern
        # for the Phase 5 grid engine; this catches the trivial case cheaply.
        CheckConstraint("parent_node_id IS NULL OR parent_node_id <> id", name="no_self_parent"),
        Index("ix_grid_nodes_parent_node_id", "parent_node_id"),
        Index("ix_grid_nodes_feeder_id", "feeder_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GridNode id={self.id} ref={self.external_ref} type={self.node_type}>"


class Site(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A physical/community location (docs/04_DATA_MODEL.md entity 3)."""

    __tablename__ = "sites"

    # RESTRICT, not CASCADE: deleting a user must not silently destroy sites,
    # meters and assets. The caller has to dismantle the site explicitly.
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(_COORD, nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(_COORD, nullable=True)
    # Nullable: a site is registered before it is mapped onto the digital twin,
    # which is exactly the Phase 1 flow (create user -> create site -> ...).
    grid_node_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("grid_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # IANA zone name. Storage stays UTC (docs/00_PROJECT_BIBLE.md section 6);
    # this is what the UI boundary localises *to*.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Kolkata")

    owner: Mapped[User] = relationship(back_populates="sites")
    grid_node: Mapped[GridNode | None] = relationship(back_populates="sites")
    meters: Mapped[list[Meter]] = relationship(
        back_populates="site", cascade="all, delete-orphan", passive_deletes=True
    )
    energy_assets: Mapped[list[EnergyAsset]] = relationship(
        back_populates="site", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("latitude IS NULL OR latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180", name="longitude_range"
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        Index("ix_sites_owner_user_id", "owner_user_id"),
        Index("ix_sites_grid_node_id", "grid_node_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Site id={self.id} name={self.name!r}>"


class Meter(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A smart/net meter (docs/04_DATA_MODEL.md entity 5)."""

    __tablename__ = "meters"

    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    meter_type: Mapped[MeterType] = mapped_column(pg_enum(MeterType, "meter_type"), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # The AMI/DISCOM-side identifier. Unique so two sites cannot both claim the
    # same physical meter, which would double-count energy at reconciliation.
    external_meter_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_level: Mapped[VerificationLevel] = mapped_column(
        pg_enum(VerificationLevel, "verification_level"),
        nullable=False,
        server_default=VerificationLevel.NONE.value,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    site: Mapped[Site] = relationship(back_populates="meters")

    __table_args__ = (
        UniqueConstraint("external_meter_ref", name="uq_meters_external_meter_ref"),
        Index("ix_meters_site_id", "site_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Meter id={self.id} type={self.meter_type} active={self.active}>"


class EnergyAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A generation or flexible-energy asset (docs/04_DATA_MODEL.md entity 6).

    Phase 1 exercises `pv` only; `battery` and `ev` exist in the vocabulary but
    have no behaviour attached yet.
    """

    __tablename__ = "energy_assets"

    site_id: Mapped[UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[EnergyAssetType] = mapped_column(
        pg_enum(EnergyAssetType, "energy_asset_type"), nullable=False
    )
    # kW per docs/00_PROJECT_BIBLE.md section 6. Numeric, not float: capacity
    # feeds pricing and settlement arithmetic where binary rounding is not
    # acceptable.
    capacity_kw: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    commissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[EnergyAssetStatus] = mapped_column(
        pg_enum(EnergyAssetStatus, "energy_asset_status"),
        nullable=False,
        server_default=EnergyAssetStatus.PLANNED.value,
    )

    site: Mapped[Site] = relationship(back_populates="energy_assets")
    inverters: Mapped[list[InverterDevice]] = relationship(
        back_populates="energy_asset", cascade="all, delete-orphan", passive_deletes=True
    )
    verification_records: Mapped[list[VerificationRecord]] = relationship(
        back_populates="energy_asset", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("capacity_kw > 0", name="capacity_positive"),
        Index("ix_energy_assets_site_id", "site_id"),
        Index("ix_energy_assets_site_id_asset_type", "site_id", "asset_type"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<EnergyAsset id={self.id} type={self.asset_type} kw={self.capacity_kw}>"


class InverterDevice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Device metadata for a PV system (docs/04_DATA_MODEL.md entity 7).

    An asset may have several inverters; the data model puts the foreign key on
    this side and declares no uniqueness on `energy_asset_id`.
    """

    __tablename__ = "inverter_devices"

    energy_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("energy_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    protocol: Mapped[InverterProtocol] = mapped_column(
        pg_enum(InverterProtocol, "inverter_protocol"),
        nullable=False,
        server_default=InverterProtocol.UNKNOWN.value,
    )
    external_device_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Free-form on purpose: it names an implementation under
    # `app/adapters/inverter/`, which is a pluggable set
    # (docs/06_OPEN_SOURCE_INTEGRATION.md). An enum here would have to change
    # every time an adapter is added.
    adapter_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    energy_asset: Mapped[EnergyAsset] = relationship(back_populates="inverters")

    __table_args__ = (
        UniqueConstraint("external_device_ref", name="uq_inverter_devices_external_device_ref"),
        Index("ix_inverter_devices_energy_asset_id", "energy_asset_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<InverterDevice id={self.id} protocol={self.protocol}>"


class VerificationRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Trust and eligibility evidence (docs/04_DATA_MODEL.md entity 8).

    Always attached to a user; optionally narrowed to one energy asset, which
    is what `POST /assets/{asset_id}/verification` in docs/05_API_SPEC.md
    produces.
    """

    __tablename__ = "verification_records"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("energy_assets.id", ondelete="CASCADE"),
        nullable=True,
    )
    verification_type: Mapped[VerificationType] = mapped_column(
        pg_enum(VerificationType, "verification_type"), nullable=False
    )
    source: Mapped[VerificationSource] = mapped_column(
        pg_enum(VerificationSource, "verification_source"), nullable=False
    )
    verification_level: Mapped[VerificationLevel] = mapped_column(
        pg_enum(VerificationLevel, "verification_level"),
        nullable=False,
        server_default=VerificationLevel.NONE.value,
    )
    status: Mapped[VerificationStatus] = mapped_column(
        pg_enum(VerificationStatus, "verification_status"),
        nullable=False,
        server_default=VerificationStatus.PENDING.value,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="verification_records")
    energy_asset: Mapped[EnergyAsset | None] = relationship(back_populates="verification_records")

    __table_args__ = (
        CheckConstraint(
            "expires_at IS NULL OR verified_at IS NULL OR expires_at > verified_at",
            name="expires_after_verified",
        ),
        CheckConstraint(
            f"status <> '{VerificationStatus.VERIFIED.value}' OR verified_at IS NOT NULL",
            name="verified_at_required_when_verified",
        ),
        Index("ix_verification_records_user_id", "user_id"),
        Index("ix_verification_records_asset_id", "asset_id"),
        # The eligibility lookup: "what verifications does this user hold, of
        # what type, in what state?"
        Index(
            "ix_verification_records_user_id_verification_type_status",
            "user_id",
            "verification_type",
            "status",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<VerificationRecord id={self.id} type={self.verification_type} "
            f"status={self.status} level={self.verification_level}>"
        )
