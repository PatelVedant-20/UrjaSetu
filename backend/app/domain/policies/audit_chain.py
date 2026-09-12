"""Canonical serialization, hashing and chain verification.

The integrity of the whole audit layer rests on one property: **the same
logical event must always produce the same bytes.** If it does not, hashes are
meaningless and a verification failure proves nothing.

Everything that could vary is therefore fixed here, in one place:

* **key order** — sorted, recursively;
* **separators** — no incidental whitespace;
* **`Decimal`** — rendered as a plain decimal string, never through `float`.
  A price or an amount that went through binary floating point before hashing
  would be a different number than the one the platform actually used;
* **`datetime`** — normalised to UTC and rendered to microseconds with an
  explicit offset, so a value that crossed a timezone boundary on the way in
  still hashes identically;
* **`UUID`** and **`StrEnum`** — their canonical string forms;
* **unicode** — not escaped, and encoded as UTF-8.

Pure and deterministic: plain values in, plain values out, no I/O and no clock.

**Chain scope is global.** One chain across the whole audit log, not one per
trade or per user. A per-entity chain would leave the deletion of an entire
entity's history undetectable, and at prototype volumes the cost of a single
chain — appends are serialised — is irrelevant next to the property it buys:
removing *any* event anywhere breaks verification.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from app.domain.interfaces.audit import (
    AuditEvent,
    ChainVerification,
    SealedAuditEvent,
)

# SHA-256: already the project's hashing choice for deterministic fingerprints
# (`grid_validation_runs.input_hash`), and its 64-character hex output is what
# `audit_events.event_hash` is sized for.
HASH_NAME = "sha256"
HASH_LENGTH = 64


def canonicalise(value: object) -> object:
    """Reduce any supported value to its canonical JSON form.

    Recursive, and deliberately strict: a type this does not understand raises
    rather than falling back on `str()`, because a silent stringification would
    hash two different objects to the same bytes.
    """
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, Enum):
        return canonicalise(value.value)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        # A plain, non-scientific decimal string. `float` never appears: the
        # value hashed must be the value the platform settled on.
        return format(value, "f")
    if isinstance(value, float):
        raise TypeError(
            "floats are not permitted in an audit payload; use Decimal so the "
            "hashed value is exactly the value the platform used"
        )
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("audit timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): canonicalise(item) for key, item in sorted(value.items())}
    if isinstance(value, Sequence):
        return [canonicalise(item) for item in value]
    raise TypeError(f"{type(value).__name__} cannot appear in an audit payload")


def canonical_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """A payload reduced to JSON-safe values, ready to store.

    The stored payload must be the canonical form, not the raw Python objects.
    Two reasons, and both are load-bearing:

    * `UUID`, `Decimal` and `datetime` are not JSON-serialisable, so a raw
      payload cannot reach a JSONB column at all;
    * verification rehydrates the event from the stored payload and re-hashes
      it. That only reproduces the original digest if what was stored is what
      was hashed. Canonicalisation is idempotent, so storing the canonical form
      makes the round trip exact.
    """
    canonical = canonicalise(payload)
    if not isinstance(canonical, dict):
        raise TypeError("an audit payload must canonicalise to an object")
    return canonical


def canonical_json(value: object) -> str:
    """The one serialization the audit layer hashes."""
    return json.dumps(
        canonicalise(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def event_fingerprint(event: AuditEvent, previous_hash: str | None) -> str:
    """The hash of one event in its position in the chain.

    Covers everything that says what happened — including both timestamps and
    the link to the predecessor — so editing any of them after the fact breaks
    verification.

    Excludes the ledger anchor by design: anchoring happens after the event is
    already recorded, and a hash that moved when evidence was published would
    invalidate the chain the publication exists to attest to.
    """
    material = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "event_time": event.event_time,
        "recorded_at": event.recorded_at,
        "actor_user_id": event.actor_user_id,
        "payload": event.with_payload_version(),
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def seal(event: AuditEvent, previous_hash: str | None) -> SealedAuditEvent:
    """Fix an event's place in the chain."""
    return SealedAuditEvent(
        event=event,
        previous_hash=previous_hash,
        event_hash=event_fingerprint(event, previous_hash),
    )


def verify_chain(sealed_events: Iterable[SealedAuditEvent]) -> ChainVerification:
    """Walk a chain in order and report the first break.

    Detects every tampering the brief requires: a modified payload, timestamp
    or entity reference changes the recomputed hash; a modified
    `previous_hash` or `event_hash` disagrees with what is recomputed; a
    missing or reordered event breaks the linkage between neighbours.

    The events must arrive in recorded order. Verification does not sort them —
    the order *is* part of what is being checked.
    """
    problems: list[str] = []
    checked = 0
    expected_previous: str | None = None
    first_broken = None

    for index, sealed in enumerate(sealed_events):
        recomputed = event_fingerprint(sealed.event, sealed.previous_hash)

        if sealed.event_hash != recomputed:
            problems.append(
                f"event {sealed.event.event_id} does not match its stored hash: "
                "its content or timestamps were altered after recording"
            )
        if sealed.previous_hash != expected_previous:
            problems.append(
                f"event {sealed.event.event_id} claims predecessor "
                f"{_short(sealed.previous_hash)} but follows {_short(expected_previous)}: "
                "an event was removed, reordered or inserted"
            )
        if index == 0 and sealed.previous_hash is not None:
            problems.append(
                f"the chain begins at event {sealed.event.event_id}, which is not a genesis "
                "event: earlier events are missing"
            )

        if problems and first_broken is None:
            first_broken = sealed.event.event_id
            return ChainVerification(
                intact=False,
                events_checked=checked,
                broken_at_event_id=first_broken,
                problems=tuple(problems),
            )

        checked += 1
        expected_previous = sealed.event_hash

    return ChainVerification(intact=True, events_checked=checked)


def _short(digest: str | None) -> str:
    if digest is None:
        return "genesis"
    return digest[:12]
