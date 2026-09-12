"""The WebSocket gateway: connect, authorize, receive, disconnect, reconnect.

docs/05_API_SPEC.md defines three routes and one rule that shapes all of this:
"Reconnect must be safe; clients refetch authoritative REST state after
reconnect."
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
from app.domain.enums import RealtimeChannel, RealtimeEventType
from app.domain.interfaces.realtime import RealtimeEvent
from app.services.realtime_service import hub

CHANNELS = ["market", "grid", "telemetry"]


def _publish(event_type: RealtimeEventType, **kw: object) -> None:
    hub.publish(RealtimeEvent(event_type=event_type, entity_type="trade", **kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Connection and authorization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("channel", CHANNELS)
def test_all_three_documented_channels_accept_a_connection(
    ws_client: TestClient, actor: User, channel: str
) -> None:
    with ws_client.websocket_connect(f"/ws/{channel}?user_id={actor.id}") as ws:
        ready = ws.receive_json()

    assert ready["event_type"] == "ready"
    assert ready["channel"] == channel
    assert (
        ready["authoritative_source"] == "rest"
    ), "the server must tell the client where authoritative state lives"


def test_an_anonymous_connection_is_refused(ws_client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect  # noqa: PLC0415

    with (
        pytest.raises(WebSocketDisconnect) as caught,
        ws_client.websocket_connect("/ws/market") as ws,
    ):
        ws.receive_json()

    assert caught.value.code == 1008


def test_an_unknown_identity_is_refused(ws_client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect  # noqa: PLC0415

    with (
        pytest.raises(WebSocketDisconnect),
        ws_client.websocket_connect(f"/ws/market?user_id={uuid.uuid4()}") as ws,
    ):
        ws.receive_json()


def test_a_suspended_identity_is_refused(
    ws_client: TestClient, actor: User, suspend_actor: Callable[[User], None]
) -> None:
    from starlette.websockets import WebSocketDisconnect  # noqa: PLC0415

    suspend_actor(actor)

    with (
        pytest.raises(WebSocketDisconnect),
        ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws,
    ):
        ws.receive_json()


def test_identity_may_also_arrive_in_the_header(ws_client: TestClient, actor: User) -> None:
    """Non-browser clients use the same header the REST API uses."""
    with ws_client.websocket_connect("/ws/grid", headers={"X-User-Id": str(actor.id)}) as ws:
        assert ws.receive_json()["event_type"] == "ready"


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def test_a_connected_client_receives_a_published_event(ws_client: TestClient, actor: User) -> None:
    trade = uuid.uuid4()
    with ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws:
        ws.receive_json()  # ready

        _publish(RealtimeEventType.TRADE_PROPOSED, entity_id=trade, trade_id=trade)

        message = ws.receive_json()

    assert message["event_type"] == "trade_proposed"
    assert message["entity_id"] == str(trade)
    assert message["trade_id"] == str(trade)


def test_a_client_only_receives_its_own_channel(ws_client: TestClient, actor: User) -> None:
    with ws_client.websocket_connect(f"/ws/telemetry?user_id={actor.id}") as ws:
        ws.receive_json()

        # A market event must not appear on the telemetry stream.
        _publish(RealtimeEventType.TRADE_PROPOSED, entity_id=uuid.uuid4())
        hub.publish(
            RealtimeEvent(
                event_type=RealtimeEventType.TELEMETRY_UPDATED,
                entity_type="meter",
                entity_id=uuid.uuid4(),
            )
        )

        message = ws.receive_json()

    assert message["event_type"] == "telemetry_updated"


def test_two_clients_on_one_channel_both_receive(ws_client: TestClient, actor: User) -> None:
    with ws_client.websocket_connect(f"/ws/grid?user_id={actor.id}") as first:
        first.receive_json()
        with ws_client.websocket_connect(f"/ws/grid?user_id={actor.id}") as second:
            second.receive_json()

            hub.publish(
                RealtimeEvent(
                    event_type=RealtimeEventType.GRID_SNAPSHOT_UPDATED,
                    entity_type="grid_snapshot",
                    entity_id=uuid.uuid4(),
                )
            )

            assert first.receive_json()["event_type"] == "grid_snapshot_updated"
            assert second.receive_json()["event_type"] == "grid_snapshot_updated"


# ---------------------------------------------------------------------------
# Disconnect and reconnect
# ---------------------------------------------------------------------------


def test_disconnecting_releases_the_subscription(ws_client: TestClient, actor: User) -> None:
    """A leaked subscription would deliver to a dead socket forever."""
    with ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws:
        ws.receive_json()
        assert hub.subscriber_count(RealtimeChannel.MARKET) == 1

    # The gateway cleans up on its own way out; give the loop a moment.
    for _ in range(50):
        if hub.subscriber_count(RealtimeChannel.MARKET) == 0:
            break
        import time  # noqa: PLC0415

        time.sleep(0.01)

    assert hub.subscriber_count(RealtimeChannel.MARKET) == 0


def test_events_published_while_disconnected_are_simply_missed(
    ws_client: TestClient, actor: User
) -> None:
    """There is no replay buffer, by design.

    The client's recovery path is a REST refetch, so a missed notification
    costs it nothing but a round trip.
    """
    with ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws:
        ws.receive_json()

    missed = uuid.uuid4()
    _publish(RealtimeEventType.TRADE_PROPOSED, entity_id=missed)

    with ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws:
        assert ws.receive_json()["event_type"] == "ready"

        live = uuid.uuid4()
        _publish(RealtimeEventType.TRADE_PROPOSED, entity_id=live)
        message = ws.receive_json()

    assert message["entity_id"] == str(
        live
    ), "a reconnected client receives new events, not a backlog"


def test_reconnecting_resumes_delivery(ws_client: TestClient, actor: User) -> None:
    for _ in range(3):
        with ws_client.websocket_connect(f"/ws/grid?user_id={actor.id}") as ws:
            ws.receive_json()
            hub.publish(
                RealtimeEvent(
                    event_type=RealtimeEventType.GRID_VALIDATION_UPDATED,
                    entity_type="grid_validation_run",
                    entity_id=uuid.uuid4(),
                )
            )
            assert ws.receive_json()["event_type"] == "grid_validation_updated"


def test_client_messages_are_ignored(ws_client: TestClient, actor: User) -> None:
    """No business operation depends on an inbound WebSocket message."""
    with ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws:
        ws.receive_json()
        ws.send_text('{"please": "settle everything"}')

        entity = uuid.uuid4()
        _publish(RealtimeEventType.ORDER_ACCEPTED, entity_id=entity)

        assert ws.receive_json()["entity_id"] == str(entity)
