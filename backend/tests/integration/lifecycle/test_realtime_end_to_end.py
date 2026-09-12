"""The whole lifecycle with a client watching, then recovering.

docs/07_CODING_PHASES.md, Phase 10 gate: "REST remains authoritative;
WebSocket updates are timely and reconnect-safe."

Two halves. First: a connected client is told about each material change as it
happens. Second: the client goes away, the world moves on without it, and a
REST refetch after reconnecting puts it back in the correct state — which is
the only recovery mechanism the architecture provides, and the reason no replay
buffer exists.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import User
from app.domain.enums import (
    GridValidationStatus,
    RealtimeChannel,
    RealtimeEventType,
    TelemetrySource,
)
from app.domain.interfaces.grid import GridMetrics, GridValidationResult
from app.domain.interfaces.realtime import RealtimeEvent
from app.domain.interfaces.telemetry import NormalizedReading
from app.services import (
    grid_validation_service,
    pricing_service,
    settlement_service,
    telemetry_service,
)
from app.services.realtime_service import hub
from app.services.settlement_service import NotReconcilableError

from .conftest import COMMITTED_KWH, DELIVERY_END, DELIVERY_START, FEEDER, Lifecycle


class _SafeEngine:
    name = "power_grid_model"
    engine_version = "1.13.162"

    def validate(self, request):  # type: ignore[no-untyped-def]
        return GridValidationResult(
            engine=self.name,
            engine_version=self.engine_version,
            status=GridValidationStatus.SAFE,
            metrics=GridMetrics(max_line_loading_pct=Decimal("45")),
        )


def _collect(channel: RealtimeChannel) -> list[dict[str, object]]:
    """Subscribe to a channel exactly as the gateway does."""
    received: list[dict[str, object]] = []
    hub.subscribe(channel, received.append)
    return received


def test_the_lifecycle_notifies_on_every_material_change(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    market = _collect(RealtimeChannel.MARKET)
    grid = _collect(RealtimeChannel.GRID)
    telemetry = _collect(RealtimeChannel.TELEMETRY)

    # --- telemetry ----------------------------------------------------
    telemetry_service.ingest_batch(
        db_session,
        [
            NormalizedReading(
                meter_id=lifecycle.seller_meter.id,
                timestamp=DELIVERY_START,
                interval_start=DELIVERY_START,
                interval_end=DELIVERY_END,
                source=TelemetrySource.SIMULATOR,
                generation_kw=Decimal("9.8000"),
                energy_kwh=Decimal("9.8000"),
            )
        ],
        # Evaluated as of the delivery window itself. Without this the reading
        # would be classified `stale` — correctly, since the window is months
        # in the past — and a stale reading is deliberately not settleable.
        at=DELIVERY_END,
    )
    assert [e["event_type"] for e in telemetry] == [RealtimeEventType.TELEMETRY_UPDATED.value]
    assert telemetry[0]["entity_type"] == "meter"
    assert (
        telemetry[0]["payload"]["quality_status"] is not None
    ), "the Phase 2 quality classification travels with the notification"

    # --- grid validation ----------------------------------------------
    validation = grid_validation_service.validate_trade(
        db_session,
        engine=_SafeEngine(),
        trade_id=lifecycle.trade.id,
        seller_node_id=lifecycle.seller_node.id,
        buyer_node_id=lifecycle.buyer_node.id,
        quantity_kwh=COMMITTED_KWH,
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )
    lifecycle.trade.grid_validation_id = validation.id
    db_session.flush()

    assert [e["event_type"] for e in grid] == [RealtimeEventType.GRID_VALIDATION_UPDATED.value]
    assert grid[0]["entity_id"] == str(validation.id)
    assert grid[0]["trade_id"] == str(lifecycle.trade.id)
    assert grid[0]["payload"]["status"] == "safe"

    # --- pricing -------------------------------------------------------
    breakdown = pricing_service.price_trade(db_session, lifecycle.trade.id)

    price_events = [e for e in market if e["event_type"] == "market_price_changed"]
    assert len(price_events) == 1
    assert price_events[0]["payload"]["final_price"] == format(breakdown.final_price, "f")
    assert price_events[0]["payload"]["base_market_price"] == format(
        breakdown.base_market_price, "f"
    ), "base and effective price stay distinguishable on the wire"

    # --- settlement -----------------------------------------------------
    settlement = settlement_service.settle_trade(db_session, lifecycle.trade.id)

    settled = [e for e in market if e["event_type"] == "settlement_updated"]
    assert any(e["entity_type"] == "settlement" for e in settled)
    final = next(e for e in settled if e["entity_type"] == "settlement")
    assert final["trade_id"] == str(lifecycle.trade.id)
    assert final["payload"]["settled_kwh"] == format(settlement.settled_kwh, "f")

    # No notification carried anything but scalars.
    for event in market + grid + telemetry:
        assert all(
            isinstance(v, str | int | bool | type(None))
            for v in event["payload"].values()  # type: ignore[union-attr]
        )


def test_a_client_recovers_missed_changes_through_rest(
    ws_client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    actor: User,
    deliver: Callable[[Decimal | None], None],
) -> None:
    """Connect, miss something, reconnect, refetch — and be correct again."""
    with ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws:
        assert ws.receive_json()["authoritative_source"] == "rest"

        first = pricing_service.price_trade(db_session, lifecycle.trade.id)
        notification = ws.receive_json()
        assert notification["event_type"] == "market_price_changed"
        assert notification["entity_id"] == str(first.id)

    # --- disconnected: the world moves on -------------------------------
    deliver(COMMITTED_KWH)
    settlement = settlement_service.settle_trade(db_session, lifecycle.trade.id)

    # --- reconnect: no backlog, and none is needed ----------------------
    with ws_client.websocket_connect(f"/ws/market?user_id={actor.id}") as ws:
        assert ws.receive_json()["event_type"] == "ready"

        # REST is the recovery path, and it knows about the settlement the
        # client never heard about.
        fetched = ws_client.get(
            f"/api/v1/settlements/{settlement.id}", headers={"X-User-Id": str(actor.id)}
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["id"] == str(settlement.id)
        assert Decimal(fetched.json()["settled_kwh"]) == settlement.settled_kwh

        # And live updates resume.
        second = pricing_service.price_trade(db_session, lifecycle.trade.id)
        resumed = ws.receive_json()

    assert resumed["event_type"] == "market_price_changed"
    assert resumed["entity_id"] == str(second.id)


def test_a_failing_subscriber_cannot_break_a_business_operation(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """Delivery is best-effort; the transaction is not."""

    def broken(_: dict[str, object]) -> None:
        raise RuntimeError("client vanished mid-write")

    hub.subscribe(RealtimeChannel.MARKET, broken)

    row = pricing_service.price_trade(db_session, lifecycle.trade.id)

    assert row.id is not None, "the price was still written and committed"
    assert pricing_service.get_breakdown(db_session, lifecycle.trade.id).id == row.id


def test_notifications_only_follow_a_committed_change(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """A refused settlement must not announce one."""
    received = _collect(RealtimeChannel.MARKET)
    pricing_service.price_trade(db_session, lifecycle.trade.id)

    with pytest.raises(NotReconcilableError):
        settlement_service.settle_trade(db_session, lifecycle.trade.id)

    settled = [
        e
        for e in received
        if e["event_type"] == "settlement_updated" and e["entity_type"] == "settlement"
    ]
    assert settled == [], "no settlement exists, so nothing may claim one does"


def test_hub_publishing_is_isolated_per_channel_during_a_real_flow(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    telemetry = _collect(RealtimeChannel.TELEMETRY)

    pricing_service.price_trade(db_session, lifecycle.trade.id)

    assert telemetry == [], "a pricing change is not telemetry news"


def test_the_event_contract_is_stable_across_a_flow(
    db_session: Session, lifecycle: Lifecycle
) -> None:
    """Every message has the fields a client binds to."""
    received = _collect(RealtimeChannel.MARKET)
    pricing_service.price_trade(db_session, lifecycle.trade.id)

    assert received
    for message in received:
        assert set(message) == {
            "event_id",
            "event_type",
            "channel",
            "occurred_at",
            "entity_type",
            "entity_id",
            "trade_id",
            "payload",
            "payload_version",
        }
        assert RealtimeEvent  # contract import is exercised
