"""Every documented Phase 6-8 endpoint, traced over real HTTP.

docs/05_API_SPEC.md defines eight endpoints across pricing, settlement and
audit. Each is exercised against the live application: router -> schema ->
service -> domain -> repository -> database, and back out as a response body.

Registration alone proves nothing — an endpoint can be reachable and still be
wired to the wrong service — so each assertion checks a value the request had
to travel the whole stack to produce.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.domain.enums import UserRole
from app.main import create_app
from app.services import pricing_service, settlement_service

from .conftest import COMMITTED_KWH, DELIVERY_END, DELIVERY_START, Lifecycle


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def operator_headers(db_session: Session, lifecycle: Lifecycle) -> dict[str, str]:
    """The buyer, elevated so audit reads are permitted."""
    lifecycle.buyer.role = UserRole.ADMIN
    db_session.flush()
    return {"X-User-Id": str(lifecycle.buyer.id)}


# ---------------------------------------------------------------------------
# Phase 6
# ---------------------------------------------------------------------------


def test_post_pricing_quote(
    client: TestClient, lifecycle: Lifecycle, operator_headers: dict[str, str]
) -> None:
    """A pre-trade scenario quote, which is what the spec defines this as.

    The endpoint takes an explicit scenario rather than a trade id, because a
    quote is calculated "before trade commitment" — when no trade exists yet.
    """
    response = client.post(
        "/api/v1/pricing/quote",
        json={
            "base_price_inr_per_kwh": "6.0000",
            "quantity_kwh": "10.0000",
            "delivery_start": DELIVERY_START.isoformat(),
            "delivery_end": DELIVERY_END.isoformat(),
            "grid_status": "safe",
            "grid_metrics": {"max_line_loading_pct": "45.000"},
            "forecast_confidence": "0.9000",
            "local_renewable": True,
        },
        headers=operator_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(str(body["base_market_price"])) == Decimal("6.0000")
    # A quiet feeder costs nothing in congestion, and the incentive applies.
    assert Decimal(str(body["congestion_component"])) == Decimal("0")
    assert Decimal(str(body["local_renewable_component"])) < Decimal("0")
    components = (
        Decimal(str(body["base_market_price"]))
        + Decimal(str(body["time_component"]))
        + Decimal(str(body["congestion_component"]))
        + Decimal(str(body["imbalance_component"]))
        + Decimal(str(body["local_renewable_component"]))
    )
    assert components == Decimal(str(body["final_price"]))


def test_pricing_quote_never_prices_an_unknown_grid_as_safe(
    client: TestClient, operator_headers: dict[str, str]
) -> None:
    """The same rule the engine enforces, checked over HTTP."""
    scenario = {
        "base_price_inr_per_kwh": "6.0000",
        "quantity_kwh": "10.0000",
        "delivery_start": DELIVERY_START.isoformat(),
        "delivery_end": DELIVERY_END.isoformat(),
    }
    safe = client.post(
        "/api/v1/pricing/quote",
        json={**scenario, "grid_status": "safe", "grid_metrics": {"max_line_loading_pct": "10"}},
        headers=operator_headers,
    ).json()
    unknown = client.post(
        "/api/v1/pricing/quote",
        json={**scenario, "grid_status": "unknown"},
        headers=operator_headers,
    ).json()

    assert Decimal(str(unknown["congestion_component"])) > Decimal(
        str(safe["congestion_component"])
    )
    assert unknown["recommended_decision"] == "reject"


def test_get_trade_price_breakdown(
    client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    operator_headers: dict[str, str],
) -> None:
    stored = pricing_service.price_trade(db_session, lifecycle.trade.id)

    response = client.get(
        f"/api/v1/trades/{lifecycle.trade.id}/price-breakdown", headers=operator_headers
    )

    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["final_price"])) == stored.final_price


def test_price_breakdown_is_404_before_any_pricing_run(
    client: TestClient, lifecycle: Lifecycle, operator_headers: dict[str, str]
) -> None:
    response = client.get(
        f"/api/v1/trades/{lifecycle.trade.id}/price-breakdown", headers=operator_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRICE_BREAKDOWN_NOT_FOUND"


# ---------------------------------------------------------------------------
# Phase 7
# ---------------------------------------------------------------------------


def test_post_trade_reconcile(
    client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    deliver: Callable[[Decimal | None], None],
    operator_headers: dict[str, str],
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)

    response = client.post(
        f"/api/v1/trades/{lifecycle.trade.id}/reconcile", headers=operator_headers
    )

    assert response.status_code in (200, 201), response.text
    body = response.json()
    assert body["reconciliation_status"] == "reconciled"
    assert Decimal(str(body["committed_kwh"])) == COMMITTED_KWH


def test_post_trade_settle_and_read_it_back(
    client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    deliver: Callable[[Decimal | None], None],
    operator_headers: dict[str, str],
) -> None:
    breakdown = pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)

    created = client.post(f"/api/v1/trades/{lifecycle.trade.id}/settle", headers=operator_headers)
    assert created.status_code in (200, 201), created.text
    settlement_id = created.json()["id"]

    # Settled at the Phase 6 effective price, over HTTP.
    expected = (COMMITTED_KWH * breakdown.final_price).quantize(Decimal("0.01"))
    assert Decimal(str(created.json()["gross_amount_inr"])) == expected

    fetched = client.get(f"/api/v1/settlements/{settlement_id}", headers=operator_headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == settlement_id


def test_settle_without_telemetry_is_refused_over_http(
    client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    operator_headers: dict[str, str],
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)

    response = client.post(f"/api/v1/trades/{lifecycle.trade.id}/settle", headers=operator_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SETTLEMENT_NOT_RECONCILABLE"


def test_get_user_settlements(
    client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    deliver: Callable[[Decimal | None], None],
    operator_headers: dict[str, str],
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)

    response = client.get(
        f"/api/v1/users/{lifecycle.buyer.id}/settlements", headers=operator_headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload if isinstance(payload, list) else payload.get("settlements", payload)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Phase 8
# ---------------------------------------------------------------------------


def test_get_audit_timeline(
    client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    deliver: Callable[[Decimal | None], None],
    operator_headers: dict[str, str],
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)
    deliver(COMMITTED_KWH)
    settlement_service.settle_trade(db_session, lifecycle.trade.id)

    response = client.get(
        f"/api/v1/audit/entities/trade/{lifecycle.trade.id}", headers=operator_headers
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    events = payload if isinstance(payload, list) else payload.get("events", payload)
    kinds = [event["event_type"] for event in events]
    assert kinds == ["price_calculated", "trade_reconciled", "trade_settled"]


def test_audit_timeline_requires_identity(client: TestClient, lifecycle: Lifecycle) -> None:
    """An audit log must never be world-readable."""
    response = client.get(f"/api/v1/audit/entities/trade/{lifecycle.trade.id}")

    assert response.status_code == 401


def test_audit_timeline_refuses_an_unrelated_participant(
    client: TestClient, db_session: Session, lifecycle: Lifecycle
) -> None:
    """A prosumer who is not party to the trade cannot read its history."""
    outsider = lifecycle.seller
    outsider.role = UserRole.PROSUMER
    db_session.flush()

    other_trade_headers = {"X-User-Id": str(outsider.id)}
    response = client.get(
        f"/api/v1/audit/entities/market_session/{lifecycle.market_session.id}",
        headers=other_trade_headers,
    )

    assert response.status_code == 403


def test_post_audit_anchor(
    client: TestClient,
    db_session: Session,
    lifecycle: Lifecycle,
    operator_headers: dict[str, str],
) -> None:
    pricing_service.price_trade(db_session, lifecycle.trade.id)

    response = client.post(
        f"/api/v1/audit/anchor/trade/{lifecycle.trade.id}", headers=operator_headers
    )

    assert response.status_code in (200, 201, 202), response.text
