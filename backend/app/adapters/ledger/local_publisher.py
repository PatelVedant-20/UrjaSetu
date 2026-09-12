"""A ledger publisher that needs no ledger.

Satisfies `DLTPublisher` by deriving a deterministic local receipt from the
event's own hash. It exists for three reasons:

* it proves the publisher boundary is implementable without a network, which is
  what keeps Hyperledger optional rather than assumed;
* it gives a demo something to show in the anchor column;
* it is a second, independent implementation of the Protocol, so the audit
  service can be exercised against a publisher that is not the real one.

It is **not** a distributed ledger and does not pretend to be. It adds no
security property the PostgreSQL chain does not already have, and it is
deliberately named so that nobody mistakes it for Fabric.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domain.interfaces.audit import LedgerAnchor, SealedAuditEvent


class LocalFilePublisher:
    """Issues a local receipt for a sealed event.

    The receipt is `local:<first 32 characters of the event hash>` — derived,
    not random, so publishing the same event twice yields the same reference
    and a retry cannot create a second anchor for one event.
    """

    name = "local"

    def publish(self, event: SealedAuditEvent) -> LedgerAnchor:
        return LedgerAnchor(
            reference=f"local:{event.event_hash[:32]}",
            publisher=self.name,
            published_at=datetime.now(UTC),
        )
