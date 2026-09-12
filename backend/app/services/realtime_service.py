"""The in-process realtime hub.

One registry of who is listening to which channel, and one `publish` that fans
an event out to them. Nothing more: docs/02_TECH_STACK.md puts Redis at "only
when multi-process realtime/background scaling requires it" and the Bible
forbids adding infrastructure a phase does not need, so this is a plain
in-memory hub inside the modular monolith. No broker, no queue server, no
second process.

**Failure isolation is the point.** A subscriber that raises, a socket that has
already gone away, a client that is too slow — none of them may affect the
business operation that triggered the event, and none may affect the other
subscribers. Every delivery is therefore individually guarded, and `publish`
cannot raise.

**Publish after commit.** Callers invoke this once the authoritative
transaction has committed. A notification that arrived before the row existed
would send clients to refetch a resource that is not there yet.

No FastAPI import appears here. The hub deals in plain callables, so services
can publish without knowing a transport exists and the whole thing is testable
without a socket.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from uuid import UUID, uuid4

from app.domain.enums import RealtimeChannel
from app.domain.interfaces.realtime import RealtimeEvent

logger = logging.getLogger(__name__)

# What the hub hands a message to. The transport decides what that means: the
# WebSocket gateway drops it on that connection's queue; a test collects it.
Subscriber = Callable[[dict[str, object]], None]


class RealtimeHub:
    """Channel subscriptions and fan-out.

    Guarded by a lock because connections are added and removed from the event
    loop while `publish` is called from the worker threads FastAPI runs sync
    endpoints on. The lock is held only long enough to copy the subscriber
    list — never while delivering — so one slow subscriber cannot block
    another's connection from closing.
    """

    def __init__(self) -> None:
        self._subscribers: dict[RealtimeChannel, dict[UUID, Subscriber]] = {
            channel: {} for channel in RealtimeChannel
        }
        self._lock = threading.Lock()

    def subscribe(self, channel: RealtimeChannel, subscriber: Subscriber) -> UUID:
        """Register a listener and return the handle used to remove it."""
        token = uuid4()
        with self._lock:
            self._subscribers[channel][token] = subscriber
        return token

    def unsubscribe(self, channel: RealtimeChannel, token: UUID) -> None:
        """Remove a listener. Unknown tokens are ignored.

        Idempotent on purpose: a disconnect can be noticed in more than one
        place, and cleaning up twice must not raise.
        """
        with self._lock:
            self._subscribers[channel].pop(token, None)

    def subscriber_count(self, channel: RealtimeChannel) -> int:
        with self._lock:
            return len(self._subscribers[channel])

    def publish(self, event: RealtimeEvent) -> int:
        """Deliver an event to its channel. Never raises.

        Returns how many subscribers accepted it, which is useful in tests and
        meaningless to callers in production — they must not branch on it.
        """
        message = event.to_message()
        with self._lock:
            targets = list(self._subscribers[event.channel].items())

        delivered = 0
        for token, subscriber in targets:
            try:
                subscriber(message)
                delivered += 1
            except Exception:
                # One broken client is not a business failure. Log, drop the
                # subscription, and carry on to the next.
                logger.warning(
                    "realtime delivery failed on %s; dropping subscriber",
                    event.channel.value,
                    exc_info=True,
                )
                self.unsubscribe(event.channel, token)
        return delivered

    def reset(self) -> None:
        """Forget every subscription. For test isolation only."""
        with self._lock:
            for channel in self._subscribers:
                self._subscribers[channel].clear()


# The single hub for the process. Services import this rather than receiving it,
# for the same reason they import a session factory: there is exactly one.
hub = RealtimeHub()


def publish(event: RealtimeEvent) -> None:
    """Publish through the process hub, swallowing any failure.

    The one function business services call. It is deliberately impossible for
    this to propagate an exception into a service that has already committed.
    """
    try:
        hub.publish(event)
    except Exception:  # pragma: no cover - the hub already guards each delivery
        logger.warning("realtime publish failed", exc_info=True)
