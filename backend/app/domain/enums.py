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


class TelemetryQualityStatus(StrEnum):
    """LOCKED — `telemetry_readings.quality_status` values.

    Fixed by docs/04_DATA_MODEL.md, entity 10. These seven are the complete
    vocabulary; adding a state is an architecture decision, not a code change.

    Exactly one status is stored per reading. When several conditions apply the
    classifier picks by a fixed precedence (see
    `app.domain.policies.telemetry_quality`), so the same input always yields
    the same status (docs/10_TESTING_AND_INTEGRATION.md: determinism).
    """

    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    OUT_OF_ORDER = "out_of_order"
    DUPLICATE = "duplicate"
    INVALID_VALUE = "invalid_value"
    SOURCE_UNAVAILABLE = "source_unavailable"

    @property
    def is_usable(self) -> bool:
        """Whether a reading with this status may be treated as measured truth.

        Aggregation counts only usable readings, and the stale-telemetry
        reliability path in docs/01_FINAL_ARCHITECTURE.md falls back to
        last-known-valid — both need this distinction.

        Note it does *not* gate `GET /sites/{site_id}/telemetry/latest` or the
        historical interval query: those return stored readings whatever their
        status, so recency never makes telemetry disappear.
        """
        return self is TelemetryQualityStatus.VALID


class TelemetrySource(StrEnum):
    """LOCKED — `telemetry_readings.source` values.

    Fixed by docs/04_DATA_MODEL.md, entity 10. These classify the *ingestion
    channel*, never a vendor or adapter implementation: naming a vendor here
    would couple the domain to it, which docs/06_OPEN_SOURCE_INTEGRATION.md
    forbids. An adapter maps itself onto one of these, so adding an adapter
    never requires a migration, and no vendor-specific value may be added.
    """

    METER = "meter"
    INVERTER = "inverter"
    SIMULATOR = "simulator"
    IMPORT = "import"
    MANUAL = "manual"


class ForecastType(StrEnum):
    """LOCKED — `forecast_runs.forecast_type` values.

    Fixed by docs/04_DATA_MODEL.md entity 11: `solar`, `load`, `surplus`.

    `SURPLUS` is listed as a forecast type in its own right, but this phase
    derives surplus from a solar and a load forecast rather than asking a
    provider for it (see `app.domain.policies.surplus`). The value stays in the
    vocabulary so a provider that predicts net surplus directly can be plugged
    in later without a migration.
    """

    SOLAR = "solar"
    LOAD = "load"
    SURPLUS = "surplus"


class ForecastRunStatus(StrEnum):
    """PROPOSED — `forecast_runs.status` values.

    docs/04_DATA_MODEL.md names the column but does not enumerate it. These are
    the states a run actually passes through: it is recorded before the
    provider is called, so a provider that hangs or raises still leaves a row
    explaining what happened (docs/00_PROJECT_BIBLE.md: traceability, and an
    adapter failure must stay observable).
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self in (ForecastRunStatus.COMPLETED, ForecastRunStatus.FAILED)

    @property
    def has_points(self) -> bool:
        """Whether forecast points may be read from a run in this state.

        Only a completed run has a full, trustworthy horizon.
        """
        return self is ForecastRunStatus.COMPLETED


__all__ = [
    "ConsentScope",
    "EnergyAssetStatus",
    "EnergyAssetType",
    "ForecastRunStatus",
    "ForecastType",
    "GridNodeType",
    "InverterProtocol",
    "MeterType",
    "TelemetryQualityStatus",
    "TelemetrySource",
    "UserRole",
    "UserStatus",
    "VerificationLevel",
    "VerificationSource",
    "VerificationStatus",
    "VerificationType",
]
