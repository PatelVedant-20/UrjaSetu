"""Cross-process refresh stream backed by the database revision, no private payloads."""

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db.models import Simulation
from app.db.session import get_session_factory
from app.services.auth_service import COOKIE, resolve

router = APIRouter()


@router.websocket("/ws/workspace")
async def stream(socket: WebSocket) -> None:
    from app.core.config import get_settings

    origin = socket.headers.get("origin")
    if (
        origin
        and origin not in get_settings().cors_allowed_origins
        and origin.split("://", 1)[-1] != socket.headers.get("host")
    ):
        await socket.close(code=1008)
        return
    token = socket.cookies.get(COOKIE)

    def read() -> int | None:
        with get_session_factory()() as db:
            if not resolve(db, token):
                return None
            sim = db.get(Simulation, 1)
            return sim.revision if sim else -1

    revision = await asyncio.to_thread(read)
    if revision is None:
        await socket.close(code=1008)
        return
    await socket.accept()
    await socket.send_json({"type": "ready", "revision": revision})
    previous = revision
    try:
        while True:
            # Receive with timeout notices a disconnected tab even when idle.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(socket.receive_text(), timeout=1)
            revision = await asyncio.to_thread(read)
            if revision is None:
                await socket.close(code=1008)
                return
            if revision != previous:
                await socket.send_json({"type": "refresh", "revision": revision})
                previous = revision
    except (WebSocketDisconnect, RuntimeError):
        return
