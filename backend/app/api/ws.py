"""WebSocket gateway.

Transport only. The three routes docs/05_API_SPEC.md defines — `/ws/market`,
`/ws/grid`, `/ws/telemetry` — and nothing else: no business logic, no database
writes, no decisions. A connection subscribes to one channel, forwards whatever
the hub publishes, and cleans itself up.

Paths are mounted exactly as the spec writes them, at the application root
rather than under `/api/v1`, alongside `/health` — the spec gives the REST base
URL as `/api/v1` and then writes these three without it.

**Reconnect semantics.** On connect the server sends one `ready` frame naming
the channel and telling the client to load its state from REST. That is the
whole recovery protocol: there is no replay buffer and no attempt at
exactly-once delivery, because docs/05_API_SPEC.md makes REST authoritative and
a reconnecting client refetches. A client that missed events while away is
correct again the moment it refetches.

**Backpressure.** Each connection has a bounded queue. A client too slow to
keep up loses the oldest notifications rather than growing memory without
limit — acceptable precisely because no notification is authoritative.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import session_scope
from app.domain.enums import RealtimeChannel, UserStatus
from app.services.realtime_service import hub

logger = logging.getLogger(__name__)

router = APIRouter()

# Bounded so one stalled client cannot grow without limit. Deep enough that a
# browser tab that briefly stops reading does not lose a burst of updates.
QUEUE_DEPTH = 64

# RFC 6455 policy violation: the connection was understood and refused.
CLOSE_POLICY_VIOLATION = 1008


def _resolve_actor(session: Session, user_id: UUID | None) -> User | None:
    """The connecting identity, or None if it cannot be established.

    Reuses the identity model the REST API already authenticates against. No
    second auth system, no tokens invented here.
    """
    if user_id is None:
        return None
    user = session.get(User, user_id)
    if user is None or user.status is not UserStatus.ACTIVE:
        return None
    return user


async def _serve(websocket: WebSocket, channel: RealtimeChannel, user_id: UUID | None) -> None:
    """Accept, subscribe, forward until the client goes away."""
    with session_scope() as session:
        from app.core.config import get_settings
        from app.services.auth_service import COOKIE, resolve

        config = get_settings()
        actor = (
            _resolve_actor(session, user_id)
            if config.app_env == "test" and config.allow_legacy_test_api
            else resolve(session, websocket.cookies.get(COOKIE))
        )
        if (
            not (config.app_env == "test" and config.allow_legacy_test_api)
            and actor
            and actor.role.value not in ("operator", "admin")
        ):
            actor = None

    if actor is None:
        # Refused before `accept`, so an unauthorized client never receives a
        # single event.
        await websocket.close(code=CLOSE_POLICY_VIOLATION, reason="identity required")
        return

    await websocket.accept()

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=QUEUE_DEPTH)

    def sink(message: dict[str, object]) -> None:
        """Hand a published message to this connection.

        Called from whichever worker thread ran the business operation, so the
        put is scheduled onto the loop rather than performed directly.
        """

        def enqueue() -> None:
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(message)

        loop.call_soon_threadsafe(enqueue)

    token = hub.subscribe(channel, sink)

    await websocket.send_json(
        {
            "event_type": "ready",
            "channel": channel.value,
            # Said explicitly so a client cannot mistake this stream for state.
            "authoritative_source": "rest",
            "message": "connected; load current state from the REST API",
        }
    )

    async def pump() -> None:
        while True:
            await websocket.send_json(await queue.get())

    async def watch() -> None:
        # Reading is how a disconnect is noticed. Anything a client sends is
        # ignored: no business operation depends on a WebSocket message
        # (docs/05_API_SPEC.md, WebSocket Rules).
        while True:
            await websocket.receive_text()

    pump_task = asyncio.create_task(pump())
    watch_task = asyncio.create_task(watch())
    try:
        done, pending = await asyncio.wait(
            {pump_task, watch_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            with contextlib.suppress(WebSocketDisconnect, asyncio.CancelledError):
                task.result()
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        logger.warning("websocket on %s failed", channel.value, exc_info=True)
    finally:
        # Always, on every exit path: a leaked subscription would deliver to a
        # dead socket forever.
        hub.unsubscribe(channel, token)
        for task in (pump_task, watch_task):
            task.cancel()


UserQuery = Annotated[UUID | None, Query(description="Connecting user's identifier")]


@router.websocket("/ws/market")
async def market_stream(websocket: WebSocket, user_id: UserQuery = None) -> None:
    """Order, clearing, trade, price and settlement notifications."""
    await _serve(websocket, RealtimeChannel.MARKET, user_id or _header_user(websocket))


@router.websocket("/ws/grid")
async def grid_stream(websocket: WebSocket, user_id: UserQuery = None) -> None:
    """Grid validation and feeder snapshot notifications."""
    await _serve(websocket, RealtimeChannel.GRID, user_id or _header_user(websocket))


@router.websocket("/ws/telemetry")
async def telemetry_stream(websocket: WebSocket, user_id: UserQuery = None) -> None:
    """Telemetry ingestion notifications."""
    await _serve(websocket, RealtimeChannel.TELEMETRY, user_id or _header_user(websocket))


def _header_user(websocket: WebSocket) -> UUID | None:
    """Identity from `X-User-Id`, matching the REST convention.

    A browser cannot set headers on a WebSocket handshake, which is why the
    query parameter exists as well. Both carry the same opaque internal
    identifier the REST API already uses, so neither introduces a secret that
    could leak through a URL.
    """
    raw = websocket.headers.get("X-User-Id")
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None
