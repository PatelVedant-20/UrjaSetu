"""Domain enumerations.

The controlled vocabularies of the UrjaSetu domain. These live in the domain
layer — not in `db/` and not in `schemas/` — because persistence, API contracts
and business policy must all agree on the same values
(docs/03_REPOSITORY_STRUCTURE.md ownership rules).

Every member's *value* is the lowercase string persisted in PostgreSQL and
returned by the API. Never rename a value without a migration: these back
native PostgreSQL enum types.

Values marked SPECIFIED are fixed by docs/04_DATA_MODEL.md. Values marked
PROPOSED were not enumerated there; they are this phase's design decisions and
are listed in the Phase 1 handoff for Yagnik's approval.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """SPECIFIED — docs/04_DATA_MODEL.md entity 1."""

    CONSUMER = "consumer"
    PROSUMER = "prosumer"
    OPERATOR = "operator"
    REGULATOR_VIEWER = "regulator_viewer"
    ADMIN = "admin"


class UserStatus(StrEnum):
    """PROPOSED — `users.status` values are not enumerated in the data model."""

    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class VerificationLevel(StrEnum):
    """PROPOSED — shared by `utility_accounts`, `meters`, `verification_records`.

    A monotonic trust ladder. `DISCOM_VERIFIED` is the level that
    docs/11_REGULATORY_AND_INDIA_CONTEXT.md describes as the precondition for
    real trading: the DISCOM has confirmed the consumer/meter against its own
    records.
    """

    NONE = "none"
    SELF_DECLARED = "self_declared"
    DOCUMENT_VERIFIED = "document_verified"
    DISCOM_VERIFIED = "discom_verified"

    @property
    def rank(self) -> int:
        """Position on the trust ladder, for comparisons in policy code.

        Defined explicitly rather than relying on declaration order so that
        inserting a level later cannot silently change existing comparisons.
        """
        return _VERIFICATION_LEVEL_RANK[self]


_VERIFICATION_LEVEL_RANK: dict[VerificationLevel, int] = {
    VerificationLevel.NONE: 0,
    VerificationLevel.SELF_DECLARED: 1,
    VerificationLevel.DOCUMENT_VERIFIED: 2,
    VerificationLevel.DISCOM_VERIFIED: 3,
}


class VerificationType(StrEnum):
    """PROPOSED — what a `verification_records` row is evidence about."""

    IDENTITY = "identity"
    UTILITY_ACCOUNT = "utility_account"
    METER = "meter"
    ENERGY_ASSET = "energy_asset"


class VerificationSource(StrEnum):
    """PROPOSED — who or what produced the evidence."""

    SELF_DECLARED = "self_declared"
    DISCOM = "discom"
    THIRD_PARTY = "third_party"
    OPERATOR = "operator"


class VerificationStatus(StrEnum):
    """PROPOSED — lifecycle of a verification record."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ConsentScope(StrEnum):
    """PROPOSED — what a consent grant covers.

    docs/04_DATA_MODEL.md describes `consents` as the trail for device/meter
    data; market participation is separated so a user can share data without
    also authorising trading.
    """

    METER_DATA = "meter_data"
    DEVICE_DATA = "device_data"
    MARKET_PARTICIPATION = "market_participation"


class GridNodeType(StrEnum):
    """PROPOSED — node classes in the distribution digital twin."""

    SUBSTATION = "substation"
    FEEDER = "feeder"
    TRANSFORMER = "transformer"
    CONNECTION_POINT = "connection_point"


class MeterType(StrEnum):
    """PROPOSED — docs/04_DATA_MODEL.md describes `meters` as "smart/net"."""

    SMART_METER = "smart_meter"
    NET_METER = "net_meter"
    GROSS_METER = "gross_meter"


class EnergyAssetType(StrEnum):
    """SPECIFIED — docs/04_DATA_MODEL.md entity 6: "`pv`, later `battery`, `ev`".

    `BATTERY` and `EV` are declared so the vocabulary is stable, but Phase 1
    exercises only `PV`. Declaring them costs nothing and avoids an
    `ALTER TYPE` migration later.
    """

    PV = "pv"
    BATTERY = "battery"
    EV = "ev"


class EnergyAssetStatus(StrEnum):
    """PROPOSED — lifecycle implied by `commissioned_at`."""

    PLANNED = "planned"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DECOMMISSIONED = "decommissioned"


class InverterProtocol(StrEnum):
    """PROPOSED — how an inverter would be talked to.

    This is device *metadata* only. Phase 1 introduces no protocol library and
    no dependency on pySunSpec2; naming the protocol here is what lets
    `app/adapters/inverter/` pick an implementation later
    (docs/06_OPEN_SOURCE_INTEGRATION.md section 2).
    """

    SUNSPEC_MODBUS_TCP = "sunspec_modbus_tcp"
    SUNSPEC_MODBUS_RTU = "sunspec_modbus_rtu"
    VENDOR_API = "vendor_api"
    SIMULATED = "simulated"
    UNKNOWN = "unknown"


__all__ = [
    "ConsentScope",
    "EnergyAssetStatus",
    "EnergyAssetType",
    "GridNodeType",
    "InverterProtocol",
    "MeterType",
    "UserRole",
    "UserStatus",
    "VerificationLevel",
    "VerificationSource",
    "VerificationStatus",
    "VerificationType",
]
