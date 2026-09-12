"""The realtime notification contract.

docs/05_API_SPEC.md fixes the shape of this layer in one line: "WebSocket is
for push updates only", and REST "is the authoritative command/query
interface". Everything here follows from that.

A `RealtimeEvent` says **what changed**, not what the new state is. It carries
the identity of an affected resource so a client knows which REST endpoint to
refetch, and a handful of scalar hints so a dashboard can render something
immediately without waiting for the round trip. It is never the source of
truth, and a client that reconstructed business state purely from these
messages would eventually be wrong.

**This is not an audit event.** `app.domain.interfaces.audit.AuditEvent` is a
permanent, hash-chained record of what happened; this is a transient hint that
a resource is stale. They have different lifetimes, different vocabularies and
different consumers, so they are deliberately different types. Reusing the
audit event as a transport payload would tie a durable legal record to the
convenience of a UI.

**Payloads are scalars only.** No ORM object, no nested structure, no
`Decimal`, no large array. A producer converts with `scalar()` at the call
site, which keeps the wire format predictable and makes it impossible to
accidentally serialise a database row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from app.domain.enums import RealtimeChannel, RealtimeEventType

# Bumped when the meaning of a field changes, so a connected client built
# against an older contract can tell.
PAYLOAD_VERSION = "1.0.0"

# What may travel in a payload. Anything else is a bug at the call site.
Scalar = str | int | bool | None


def scalar(value: object) -> Scalar:
    """Reduce a domain value to something a wire payload may carry.

    `Decimal` becomes a plain decimal string rather than a float: a price sent
    as a float would render differently from the same price fetched over REST,
    and the two disagreeing on screen is worse than either being slightly
    late.
    """
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(
        f"{type(value).__name__} cannot travel in a realtime payload; "
        "realtime messages carry scalars, not objects"
    )


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    """One notification that a resource changed.

    `entity_type` and `entity_id` are the whole point: together they tell a
    client exactly which REST resource to refetch. `trade_id` is carried
    separately when the change concerns a trade, because the trade is the
    lifecycle key a dashboard groups by — the same correlation the audit
    timeline uses.
    """

    event_type: RealtimeEventType
    entity_type: str
    entity_id: UUID | None = None
    trade_id: UUID | None = None
    payload: Mapping[str, Scalar] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: UUID = field(default_factory=uuid4)

    @property
    def channel(self) -> RealtimeChannel:
        return self.event_type.channel

    def to_message(self) -> dict[str, object]:
        """The JSON object sent on the wire.

        Flat, small and stable. `event_id` lets a client discard a duplicate;
        `occurred_at` lets it ignore one that arrives late. Neither is required
        for correctness — refetching REST is — but both make the client's job
        easier.
        """
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type.value,
            "channel": self.channel.value,
            "occurred_at": self.occurred_at.astimezone(UTC).isoformat(),
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "trade_id": str(self.trade_id) if self.trade_id else None,
            "payload": dict(self.payload),
            "payload_version": PAYLOAD_VERSION,
        }


@runtime_checkable
class RealtimePublisher(Protocol):
    """Where a business service hands off a notification.

    Publishing must never be able to affect the operation that triggered it:
    implementations swallow and log delivery failures rather than raising, and
    are called only *after* the business transaction has committed.
    """

    def publish(self, event: RealtimeEvent) -> None:
        """Deliver to everyone currently listening on the event's channel."""
        ...
