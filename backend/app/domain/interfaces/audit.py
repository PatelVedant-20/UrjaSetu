"""The audit contract.

The stable boundary between UrjaSetu's business phases and whatever records
what they decided:

    domain action -> AuditEvent -> seal -> SealedAuditEvent -> audit_events
                                                           -> optional ledger

docs/00_PROJECT_BIBLE.md states the requirement this implements: "Every
material business decision must be explainable from stored inputs and outputs."
docs/01_FINAL_ARCHITECTURE.md places the `audit` module last in the loop, and
docs/06_OPEN_SOURCE_INTEGRATION.md is explicit that a ledger is optional and
that "operational market data stays in PostgreSQL".

**Two types, one concept.** An `AuditEvent` is what a business service
describes: what happened, to what, when, and with which values. A
`SealedAuditEvent` is that event once the chain has closed over it — the same
content plus the link to its predecessor and its own hash. They are separate so
that hashing is an explicit step performed in exactly one place, rather than
something a caller might forget or do differently.

**PostgreSQL is the audit source of truth.** A ledger, if one is ever
configured, anchors evidence that already exists. Nothing here requires a
blockchain, a Fabric network, or any external node to function.

**Privacy.** A payload carries stable internal identifiers and decision values.
It never carries credentials, secrets, tokens or personal details
(docs/00_PROJECT_BIBLE.md section 8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.enums import AuditEntityType, AuditEventType

# What a payload may contain once canonicalised. The serializer accepts
# `Decimal`, `datetime`, `UUID` and `StrEnum` too and normalises them; these
# are what they become.
JsonValue = str | int | bool | None | Mapping[str, object] | Sequence[object]

# The shape of the payload contract itself, carried inside every payload under
# a reserved key. Bumped when the meaning of a field changes, so an old event
# stays interpretable under the contract that wrote it.
PAYLOAD_VERSION = "1.0.0"
PAYLOAD_VERSION_KEY = "payload_version"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One material business event, before the chain closes over it.

    Self-describing by design: an auditor reading a single row should be able
    to say what happened, to which entity, when, on whose behalf, and with
    which values — without joining to the tables that produced it, which may
    themselves have moved on.
    """

    event_id: UUID
    event_type: AuditEventType
    entity_type: AuditEntityType
    entity_id: UUID
    # When the business event happened.
    event_time: datetime
    # When the audit log recorded it. Separate, because the two differ whenever
    # an event is recorded after the fact, and an auditor needs both.
    recorded_at: datetime
    # Who caused it. `None` for platform-initiated events such as clearing —
    # an absent actor is not an anonymous one.
    actor_user_id: UUID | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def with_payload_version(self) -> dict[str, object]:
        """The payload as stored, carrying its own contract version.

        The version travels inside the payload rather than in a column:
        docs/04_DATA_MODEL.md entity 21 does not define one, and a reserved key
        keeps the schema as documented while still letting a reader tell which
        contract wrote the values.
        """
        return {PAYLOAD_VERSION_KEY: PAYLOAD_VERSION, **dict(self.payload)}


@dataclass(frozen=True, slots=True)
class SealedAuditEvent:
    """An audit event with its place in the chain fixed.

    `previous_hash` is `None` for exactly one event — the genesis of the chain.
    Every other event names its predecessor, so removing, reordering or editing
    any event breaks the link that follows it.

    `event_hash` covers the whole event including `previous_hash`, `event_time`
    and `recorded_at`. It deliberately does **not** cover the ledger anchor:
    anchoring happens after the fact, and a hash that changed when evidence was
    published would invalidate the very chain the publication attests to.
    """

    event: AuditEvent
    previous_hash: str | None
    event_hash: str

    @property
    def is_genesis(self) -> bool:
        return self.previous_hash is None


@dataclass(frozen=True, slots=True)
class ChainVerification:
    """The result of walking an audit chain.

    Reports the first break rather than stopping at it silently, so an operator
    learns both that the chain is broken and where.
    """

    intact: bool
    events_checked: int
    # The event at which the chain stops being verifiable, if any.
    broken_at_event_id: UUID | None = None
    problems: Sequence[str] = field(default_factory=tuple)

    @property
    def summary(self) -> str:
        if self.intact:
            return f"chain intact across {self.events_checked} events"
        return f"chain broken after {self.events_checked} events: " + "; ".join(self.problems)


# ---------------------------------------------------------------------------
# Optional ledger anchoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LedgerAnchor:
    """Evidence that an event's hash was published somewhere external.

    `reference` is whatever the ledger returns as proof — a transaction id, a
    receipt, a file path for a local publisher. UrjaSetu stores it and never
    interprets it.
    """

    reference: str
    publisher: str
    published_at: datetime


@runtime_checkable
class DLTPublisher(Protocol):
    """Where audit evidence may optionally be anchored.

    A boundary, not a requirement. docs/06_OPEN_SOURCE_INTEGRATION.md lists
    Hyperledger Fabric as an *optional later* audit layer and keeps operational
    data in PostgreSQL; the platform must work with no publisher configured at
    all, and does.

    Implementations live in `app/adapters/ledger/` and are the only place a
    ledger library may be imported. A future `HyperledgerFabricPublisher`
    satisfies this Protocol and changes nothing else.

    **What is published is evidence, never data.** A publisher receives the
    event's hash and its identifying references — not telemetry, not personal
    information, not the operational database. What it does with them is its
    own business.
    """

    @property
    def name(self) -> str:
        """Stable identifier, recorded alongside the anchor."""
        ...

    def publish(self, event: SealedAuditEvent) -> LedgerAnchor:
        """Anchor one sealed event and return the proof.

        May fail. A publisher outage must never stop the platform: the
        PostgreSQL record is already authoritative by the time this is called,
        and anchoring is a second, optional step.
        """
        ...
