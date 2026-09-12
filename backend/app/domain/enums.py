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


class MarketType(StrEnum):
    """LOCKED — `market_sessions.market_type` values.

    docs/04_DATA_MODEL.md entity 13 specifies `day_ahead` initially, and
    docs/00_PROJECT_BIBLE.md section 7 locks day-ahead commitment as the first
    market mode because that is what the Indian P2P pilot material describes
    (docs/11_REGULATORY_AND_INDIA_CONTEXT.md).

    Continuous/intra-day trading is deliberately absent: adding it is a market
    design decision, not a code change.
    """

    DAY_AHEAD = "day_ahead"


class MarketSessionStatus(StrEnum):
    """LOCKED — `market_sessions.status` values.

    Exactly three, matching the endpoints in docs/05_API_SPEC.md that move a
    session through its life: create/open, close order intake, then clear. A
    session is never abandoned mid-life in this design; adding a state is an
    architecture decision, not a code change.
    """

    OPEN = "open"
    CLOSED = "closed"
    CLEARED = "cleared"

    @property
    def accepts_orders(self) -> bool:
        """Only an open session takes new orders."""
        return self is MarketSessionStatus.OPEN

    @property
    def can_clear(self) -> bool:
        """Clearing runs once, after intake closes.

        Clearing an open session would match against a book that is still
        changing; clearing a cleared one would double-commit the same energy.
        """
        return self is MarketSessionStatus.CLOSED


class OrderSide(StrEnum):
    """LOCKED — `orders.side` values (docs/04_DATA_MODEL.md entity 14)."""

    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> OrderSide:
        return OrderSide.SELL if self is OrderSide.BUY else OrderSide.BUY


class OrderStatus(StrEnum):
    """LOCKED — `orders.status` values.

    Partial fills are represented explicitly because an order may be filled by
    several counterparties, and the remainder has to stay visible in the book.
    The vocabulary is about *fill*, not about matching: an order is filled by
    the energy committed to it, whichever engine paired it.
    """

    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    @property
    def is_active(self) -> bool:
        """Whether the order still has energy that can be matched."""
        return self in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)

    @property
    def is_terminal(self) -> bool:
        return not self.is_active


class TradeStatus(StrEnum):
    """LOCKED — `trades.status` values, for Phase 4.

    One value, deliberately. Everything clearing produces is a *candidate*:
    docs/05_API_SPEC.md is explicit that clearing "does not silently bypass
    grid validation".

    Approval and commitment states are **not** declared here. Declaring them
    now would let code branch on outcomes no phase can yet produce, and would
    imply a trade lifecycle that grid validation (Phase 5), dynamic pricing
    (Phase 6) and settlement (Phase 7) have not yet defined. They arrive with
    the phases that own them, as an `ALTER TYPE ... ADD VALUE` migration.
    """

    PROPOSED = "proposed"


class GridValidationStatus(StrEnum):
    """LOCKED — what a validation was able to conclude about the network.

    Three states, not two, because "we could not tell" is a real outcome and
    must never collapse into either of the others:

    * ``SAFE``    — the network was solved and is within every operating limit.
    * ``UNSAFE``  — the network was solved and breaches at least one limit.
    * ``UNKNOWN`` — no trustworthy conclusion was reached: the solver failed or
      did not converge, or the twin was missing information the judgement
      depends on (a line with no rating cannot be assessed for overload).

    A boolean cannot express this. With only `safe`/`not safe`, a solver crash
    has to be recorded as one of them: as safe it silently approves an
    unexamined trade, as unsafe it reports a violation that was never observed.
    `UNKNOWN` is neither — it blocks the trade exactly as `UNSAFE` does, while
    recording honestly that the grid was never actually cleared.
    """

    SAFE = "safe"
    UNSAFE = "unsafe"
    UNKNOWN = "unknown"

    @property
    def permits_trade(self) -> bool:
        """Only a network positively shown to be safe lets a trade through.

        Both other states block it. Missing information is never a pass
        (docs/00_PROJECT_BIBLE.md: deterministic safety).
        """
        return self is GridValidationStatus.SAFE

    @property
    def was_evaluated(self) -> bool:
        """Whether the network was actually solved, whatever the verdict."""
        return self is not GridValidationStatus.UNKNOWN


class GridValidationDecision(StrEnum):
    """LOCKED — `grid_validation_runs.decision` values.

    Fixed by the core loop in docs/00_PROJECT_BIBLE.md section 4:

        GRID VALIDATION -> ACCEPT / REPRICE / REDUCE / SHIFT / REJECT

    This phase emits only `ACCEPT` and `REJECT`: it answers "is this trade
    safe?". Choosing a *remedy* for an unsafe trade — reprice, reduce the
    quantity, shift the window — is the grid-aware market feedback that
    docs/07_CODING_PHASES.md assigns to a later phase, and it consumes the
    violations recorded here rather than re-deriving them.

    The remediation values are declared because the Bible locks the vocabulary,
    not because anything yet produces them.
    """

    ACCEPT = "accept"
    REPRICE = "reprice"
    REDUCE = "reduce"
    SHIFT = "shift"
    REJECT = "reject"

    @property
    def is_safe(self) -> bool:
        """Whether the trade may proceed as proposed, unchanged."""
        return self is GridValidationDecision.ACCEPT

    @property
    def requires_remediation(self) -> bool:
        """Whether a later phase must alter the trade before it can proceed."""
        return self in (
            GridValidationDecision.REPRICE,
            GridValidationDecision.REDUCE,
            GridValidationDecision.SHIFT,
        )


class GridViolationType(StrEnum):
    """PROPOSED — the constraint classes a power flow can breach.

    docs/04_DATA_MODEL.md entity 17 records min/max voltage, max line loading
    and max transformer loading, and docs/06_OPEN_SOURCE_INTEGRATION.md names
    the same three as the normalised adapter output. These are those three
    constraints, with voltage split by direction because an under-voltage and
    an over-voltage have opposite causes and opposite remedies.

    Deliberately no LOW/MEDIUM/HIGH congestion grading: no project document
    defines such a vocabulary, and a violation already carries the measured
    value and the limit it breached, which is strictly more information than a
    band would be.
    """

    UNDER_VOLTAGE = "under_voltage"
    OVER_VOLTAGE = "over_voltage"
    LINE_OVERLOAD = "line_overload"
    TRANSFORMER_OVERLOAD = "transformer_overload"

    @property
    def is_voltage(self) -> bool:
        return self in (
            GridViolationType.UNDER_VOLTAGE,
            GridViolationType.OVER_VOLTAGE,
        )

    @property
    def is_loading(self) -> bool:
        return self in (
            GridViolationType.LINE_OVERLOAD,
            GridViolationType.TRANSFORMER_OVERLOAD,
        )


__all__ = [
    "ConsentScope",
    "EnergyAssetStatus",
    "EnergyAssetType",
    "ForecastRunStatus",
    "ForecastType",
    "GridNodeType",
    "GridValidationDecision",
    "GridValidationStatus",
    "GridViolationType",
    "InverterProtocol",
    "MarketSessionStatus",
    "MarketType",
    "MeterType",
    "OrderSide",
    "OrderStatus",
    "TelemetryQualityStatus",
    "TradeStatus",
    "TelemetrySource",
    "UserRole",
    "UserStatus",
    "VerificationLevel",
    "VerificationSource",
    "VerificationStatus",
    "VerificationType",
]
