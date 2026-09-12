"""The realtime event contract itself.

Pure: no database, no socket. Checks the properties a client depends on — that
a message is small, JSON-safe, self-describing, and says which REST resource to
refetch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.enums import RealtimeChannel, RealtimeEventType
from app.domain.interfaces.realtime import (
    PAYLOAD_VERSION,
    RealtimeEvent,
    RealtimePublisher,
    scalar,
)
from app.services.realtime_service import RealtimeHub, hub


def test_every_event_type_maps_to_exactly_one_channel() -> None:
    for event_type in RealtimeEventType:
        assert isinstance(event_type.channel, RealtimeChannel)


def test_channels_are_exactly_the_three_the_api_spec_defines() -> None:
    assert {c.value for c in RealtimeChannel} == {"market", "grid", "telemetry"}


def test_a_message_is_json_serialisable_and_compact() -> None:
    event = RealtimeEvent(
        event_type=RealtimeEventType.TRADE_PROPOSED,
        entity_type="trade",
        entity_id=uuid4(),
        trade_id=uuid4(),
        payload={"quantity_kwh": "10.0000", "status": "proposed"},
    )

    encoded = json.dumps(event.to_message())

    assert len(encoded) < 1024, "realtime messages stay small"
    decoded = json.loads(encoded)
    assert decoded["payload_version"] == PAYLOAD_VERSION
    assert decoded["entity_type"] == "trade"
    assert decoded["channel"] == "market"


def test_a_message_identifies_the_resource_to_refetch() -> None:
    """The contract's whole job: say what changed, not what it now is."""
    trade = uuid4()
    message = RealtimeEvent(
        event_type=RealtimeEventType.MARKET_PRICE_CHANGED,
        entity_type="price_components",
        entity_id=uuid4(),
        trade_id=trade,
    ).to_message()

    assert message["entity_type"] == "price_components"
    assert message["entity_id"] is not None
    assert message["trade_id"] == str(trade)


def test_duplicate_notifications_are_distinguishable() -> None:
    """A client must be able to discard a repeat without harm."""
    a = RealtimeEvent(event_type=RealtimeEventType.TELEMETRY_UPDATED, entity_type="meter")
    b = RealtimeEvent(event_type=RealtimeEventType.TELEMETRY_UPDATED, entity_type="meter")

    assert a.to_message()["event_id"] != b.to_message()["event_id"]


def test_decimals_travel_as_exact_strings_never_floats() -> None:
    """A price on the wire must read the same as the price over REST."""
    assert scalar(Decimal("6.5100")) == "6.5100"
    assert not isinstance(scalar(Decimal("6.5100")), float)


def test_timestamps_are_normalised_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    assert scalar(datetime(2026, 6, 2, 12, 0, tzinfo=ist)) == scalar(
        datetime(2026, 6, 2, 6, 30, tzinfo=UTC)
    )


def test_an_object_cannot_travel_in_a_payload() -> None:
    """No ORM row, no nested structure, no accidental serialization."""
    with pytest.raises(TypeError):
        scalar(object())


def test_the_hub_satisfies_the_publisher_protocol() -> None:
    assert isinstance(hub, RealtimePublisher)


# ---------------------------------------------------------------------------
# Fan-out and isolation
# ---------------------------------------------------------------------------


def test_events_reach_only_their_own_channel() -> None:
    local = RealtimeHub()
    market: list[dict[str, object]] = []
    grid: list[dict[str, object]] = []
    local.subscribe(RealtimeChannel.MARKET, market.append)
    local.subscribe(RealtimeChannel.GRID, grid.append)

    local.publish(RealtimeEvent(event_type=RealtimeEventType.TRADE_PROPOSED, entity_type="trade"))

    assert len(market) == 1
    assert grid == [], "a market change must not reach grid subscribers"


def test_multiple_clients_on_one_channel_all_receive() -> None:
    local = RealtimeHub()
    seen = [[], []]  # type: ignore[var-annotated]
    local.subscribe(RealtimeChannel.GRID, seen[0].append)
    local.subscribe(RealtimeChannel.GRID, seen[1].append)

    local.publish(
        RealtimeEvent(
            event_type=RealtimeEventType.GRID_VALIDATION_UPDATED, entity_type="grid_validation_run"
        )
    )

    assert len(seen[0]) == 1 and len(seen[1]) == 1


def test_one_broken_client_does_not_affect_the_others() -> None:
    """Delivery failure is isolated, and the broken subscription is dropped."""
    local = RealtimeHub()
    good: list[dict[str, object]] = []

    def broken(_: dict[str, object]) -> None:
        raise RuntimeError("socket already closed")

    local.subscribe(RealtimeChannel.MARKET, broken)
    local.subscribe(RealtimeChannel.MARKET, good.append)

    delivered = local.publish(
        RealtimeEvent(event_type=RealtimeEventType.ORDER_ACCEPTED, entity_type="order")
    )

    assert delivered == 1
    assert len(good) == 1
    assert local.subscriber_count(RealtimeChannel.MARKET) == 1, "the broken one is dropped"


def test_publishing_never_raises_into_the_caller() -> None:
    """A business operation has already committed by the time this runs."""
    local = RealtimeHub()

    def broken(_: dict[str, object]) -> None:
        raise RuntimeError("boom")

    local.subscribe(RealtimeChannel.TELEMETRY, broken)

    local.publish(
        RealtimeEvent(event_type=RealtimeEventType.TELEMETRY_UPDATED, entity_type="meter")
    )


def test_unsubscribing_is_idempotent() -> None:
    local = RealtimeHub()
    token = local.subscribe(RealtimeChannel.MARKET, lambda _: None)

    local.unsubscribe(RealtimeChannel.MARKET, token)
    local.unsubscribe(RealtimeChannel.MARKET, token)

    assert local.subscriber_count(RealtimeChannel.MARKET) == 0
