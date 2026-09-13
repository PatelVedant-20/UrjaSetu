"""Real PostgreSQL/API tests for the complete authenticated trading workflow."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import JournalEntry, Receipt, TelemetryReading, TradeAllocation
from app.db.session import dispose_engine, get_session_factory
from app.domain.policies.community_energy import IST, profile
from app.main import create_app
from app.services.workspace_service import advance, bootstrap
from tests.conftest import run_alembic_ok

HEADERS = {"X-Requested-With": "UrjaSetu"}
PASSWORD = "Sunshine2026!"


@pytest.fixture
def app(empty_database, monkeypatch):
    run_alembic_ok("upgrade", "head", db_url=empty_database)
    dispose_engine()
    monkeypatch.setenv("DATABASE_URL", empty_database)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ALLOW_LEGACY_TEST_API", "false")
    monkeypatch.setenv("SIMULATION_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    with get_session_factory()() as db:
        bootstrap(db, PASSWORD)
    yield create_app()
    dispose_engine()
    get_settings.cache_clear()


def client_for(app, email):
    client = TestClient(app, headers=HEADERS)
    result = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert result.status_code == 200, result.text
    return client


def place(client, side, quantity="0.3", price="5"):
    data = client.get("/api/v1/workspace").json()
    clock = datetime.fromisoformat(data["simulation"]["clock"]).astimezone(IST)
    start = (clock + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    result = client.post(
        "/api/v1/workspace/orders",
        json={"side": side, "quantity": quantity, "price": price, "start": start.isoformat()},
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_indian_profile_energy_balance_and_local_daylight():
    midnight = datetime(2026, 9, 13, 0, tzinfo=IST).astimezone(UTC)
    assert profile(midnight, 6)["generation_kw"] == 0
    noon = profile(midnight + timedelta(hours=12), 6)
    assert 0 < noon["generation_kw"] <= 6
    assert (
        noon["generation_kwh"] + noon["grid_import_kwh"]
        == noon["load_kwh"] + noon["grid_export_kwh"]
    )
    assert (
        profile(midnight + timedelta(hours=12), 6, scenario="cloudy")["generation_kw"]
        < noon["generation_kw"]
    )


def test_direct_purchase_uses_existing_order_partial_fills_and_retries(app):
    from uuid import uuid4

    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    offer = place(seller, "sell", "0.4", "4")
    own = place(buyer, "buy", "0.4", "8")
    url = f"/api/v1/workspace/orders/{offer['id']}/accept"
    payload = {
        "quantity": "0.2",
        "price": "8",
        "request_id": str(uuid4()),
        "own_order_id": own["id"],
    }
    first = buyer.post(url, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "committed"
    assert buyer.post(url, json=payload).json()["id"] == first.json()["id"]
    assert buyer.post(url, json={**payload, "quantity": "0.1"}).status_code == 409
    second = buyer.post(url, json={**payload, "request_id": str(uuid4())})
    assert second.status_code == 201, second.text
    data = buyer.get("/api/v1/workspace/dashboard").json()
    assert len(data["trades"]) == 2
    assert data["orders"][0]["status"] == "filled"
    assert not data["order_book"]
    operator = client_for(app, "operator@urjasetu.demo")
    operator.post("/api/v1/workspace/control", json={"action": "deliver"})
    settled = buyer.get("/api/v1/workspace/dashboard").json()
    assert len(settled["settlements"]) == 2
    assert sum(Decimal(r["settled_kwh"]) for r in settled["settlements"]) == Decimal("0.4")


def test_direct_rejection_rolls_back_and_concurrent_buyers_cannot_overfill(app):
    from uuid import uuid4

    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    other = client_for(app, "ravi@urjasetu.demo")
    offer = place(seller, "sell", "0.3", "4")
    url = f"/api/v1/workspace/orders/{offer['id']}/accept"
    payload = {"quantity": "0.3", "price": "8", "request_id": str(uuid4())}
    assert seller.post(url, json=payload).status_code == 409
    assert buyer.post(url, json={**payload, "price": "1"}).status_code == 409
    assert buyer.get("/api/v1/workspace").json()["orders"] == []
    assert seller.get("/api/v1/workspace").json()["orders"][0]["status"] == "open"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda c: c.post(url, json={**payload, "request_id": str(uuid4())}).status_code,
                [buyer, other],
            )
        )
    assert sorted(results) == [201, 409]
    assert len(buyer.get("/api/v1/workspace").json()["trades"]) == 1


def test_real_clock_worker_closes_delivery_and_settles_without_operator(app, monkeypatch):
    from uuid import uuid4

    from app.db.models import Simulation
    from app.services import experience_service

    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    offer = place(seller, "sell", "0.1", "4")
    accepted = buyer.post(
        f"/api/v1/workspace/orders/{offer['id']}/accept",
        json={"quantity": "0.1", "price": "8", "request_id": str(uuid4())},
    )
    assert accepted.status_code == 201
    completed = datetime.fromisoformat(accepted.json()["delivery_end"])

    class DeliveryClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return completed.astimezone(tz)

    monkeypatch.setattr(experience_service, "datetime", DeliveryClock)
    with get_session_factory()() as db:
        db.get(Simulation, 1).live_mode = True
        db.commit()
        experience_service.tick(db)
        count = len(list(db.scalars(select(TelemetryReading))))
        experience_service.tick(db)
        assert len(list(db.scalars(select(TelemetryReading)))) == count
        assert len(list(db.scalars(select(TradeAllocation)))) == 1
        assert sum(db.scalars(select(JournalEntry.amount_inr))) == 0
    data = buyer.get("/api/v1/workspace/dashboard").json()
    assert data["trades"][0]["status"] == "settled"
    assert len(data["settlements"]) == 1
    assert Decimal(data["settlements"][0]["settled_kwh"]) == Decimal("0.1")


def test_profile_registration_shared_stats_series_and_private_assistant(app, monkeypatch):
    from app.services import experience_service

    client = TestClient(app, headers=HEADERS)
    result = client.post(
        "/api/v1/auth/register",
        json={
            "email": "personal@example.test",
            "password": PASSWORD,
            "name": "Meera Joshi",
            "role": "prosumer",
            "capacity_kw": 3,
            "setup": {"monthly_kwh": 180, "occupants": 2, "ac_count": 0, "city": "Surat"},
        },
    )
    assert result.status_code == 201, result.text
    data = client.get("/api/v1/workspace/dashboard").json()
    assert data["profile"]["city"] == "Surat"
    assert 5.6 < data["periods"]["day"]["load_kwh"] < 6.4
    assert len(data["daily"]) >= 30
    user_id = data["user"]["id"]
    community = client_for(app, "ravi@urjasetu.demo")
    member = next(
        m
        for m in community.get("/api/v1/workspace/dashboard").json()["members"]
        if m["id"] == user_id
    )
    assert member["periods"]["day"]["load_kwh"] == data["periods"]["day"]["load_kwh"]
    assert member["node_id"] in {n["id"] for n in data["nodes"]}
    t = datetime(2026, 9, 13, 12, tzinfo=IST)
    monkeypatch.setattr(experience_service, "now", lambda db: t)
    first = client.get("/api/v1/workspace/series").json()
    assert len(first["points"]) == 180
    monkeypatch.setattr(experience_service, "now", lambda db: t + timedelta(seconds=5))
    second = client.get("/api/v1/workspace/series").json()
    assert first["points"][-1] != second["points"][-1]
    assert first["points"][1:] == second["points"][:-1]
    assert client.get("/api/v1/workspace/series?window=day&resolution=5s").status_code == 422
    assert client.get("/api/v1/workspace/series?window=day&resolution=15m").status_code == 200
    assert (
        client.put(
            "/api/v1/workspace/profile", json={**data["profile"], "share_stats": False}
        ).status_code
        == 200
    )
    private = next(
        m
        for m in community.get("/api/v1/workspace/dashboard").json()["members"]
        if m["id"] == user_id
    )
    assert private["periods"] is None and private["live"] is None
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    response = client.post("/api/v1/workspace/assistant", json={"message": "Explain my savings"})
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "account-guide"
    assert "₹7.00/kWh" in response.json()["message"]


def test_after_indian_midnight_only_tomorrows_slots_are_offered(app):
    seller = client_for(app, "asha@urjasetu.demo")
    with get_session_factory()() as db:
        advance(db, intervals=73)  # Initial 11:45 IST -> next day 06:00 IST.
    data = seller.get("/api/v1/workspace").json()
    tomorrow = (
        datetime.fromisoformat(data["simulation"]["clock"]).astimezone(IST) + timedelta(days=1)
    ).date()
    assert len(data["forecasts"]) == 192
    assert all(
        datetime.fromisoformat(p["interval_start"]).astimezone(IST).date() == tomorrow
        for p in data["forecasts"]
    )


def test_login_ownership_logout_and_revoked_socket(app):
    anonymous = TestClient(app, headers=HEADERS)
    assert anonymous.get("/api/v1/workspace").status_code == 401
    assert (
        anonymous.post(
            "/api/v1/auth/login", json={"email": "asha@urjasetu.demo", "password": "badpassword"}
        ).status_code
        == 401
    )
    assert (
        anonymous.get(
            "/api/v1/users/10000000-0000-0000-0000-000000000001",
            headers={"X-User-Id": "10000000-0000-0000-0000-000000000001"},
        ).status_code
        == 403
    )
    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    order = place(seller, "sell", price="4")
    assert buyer.post(f"/api/v1/workspace/orders/{order['id']}/cancel").status_code == 404
    assert buyer.post("/api/v1/workspace/clear").status_code == 403
    assert buyer.get("/api/v1/workspace").json()["orders"] == []
    assert (
        buyer.post(
            "/api/v1/workspace/orders",
            json={"side": "sell", "quantity": 1, "price": 4, "start": order["delivery_start"]},
        ).status_code
        == 403
    )
    with seller.websocket_connect("/ws/workspace") as ws:
        assert ws.receive_json()["type"] == "ready"
        place(buyer, "buy", price="6")
        assert ws.receive_json()["type"] == "refresh"
    cookie = seller.cookies.get("urjasetu_session")
    assert seller.post("/api/v1/auth/logout").status_code == 200
    seller.cookies.set("urjasetu_session", cookie)
    assert seller.get("/api/v1/workspace").status_code == 401


def test_reservations_complete_trade_settlement_and_idempotence(app):
    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    operator = client_for(app, "operator@urjasetu.demo")
    order = place(seller, "sell", "0.4", "4")
    overflow = seller.post(
        "/api/v1/workspace/orders",
        json={"side": "sell", "quantity": 1, "price": 4, "start": order["delivery_start"]},
    )
    assert overflow.status_code == 409
    place(buyer, "buy", "0.4", "6")
    result = operator.post("/api/v1/workspace/clear")
    assert result.status_code == 200, result.text
    assert result.json()["trades"][0]["status"] == "committed", result.text
    assert operator.post("/api/v1/workspace/clear").json()["trades"] == []
    result = operator.post("/api/v1/workspace/control", json={"action": "deliver"})
    assert result.status_code == 200, result.text
    data = seller.get("/api/v1/workspace").json()
    assert data["trades"][0]["status"] == "settled"
    assert len(data["settlements"]) == 1
    assert Decimal(str(data["settlements"][0]["settled_kwh"])) == Decimal("0.4")
    assert data["receipts"][0]["status"] == "pending"
    with get_session_factory()() as db:
        assert sum(db.scalars(select(JournalEntry.amount_inr))) == 0
        assert len(list(db.scalars(select(TradeAllocation)))) == 1
        receipt = db.scalar(select(Receipt))
        assert receipt.payload["source"] == "synthetic"
    operator.post("/api/v1/workspace/control", json={"action": "step"})
    assert len(seller.get("/api/v1/workspace").json()["settlements"]) == 1


def test_unsafe_grid_and_missing_data_do_not_settle(app):
    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    operator = client_for(app, "operator@urjasetu.demo")
    place(seller, "sell", price="4")
    place(buyer, "buy", price="6")
    operator.post(
        "/api/v1/workspace/control", json={"action": "scenario", "scenario": "congestion"}
    )
    response = operator.post("/api/v1/workspace/clear")
    assert response.status_code == 200, response.text
    assert response.json()["trades"][0]["status"] == "rejected"
    assert seller.get("/api/v1/workspace").json()["settlements"] == []


def test_signup_and_csrf(app):
    client = TestClient(app)
    payload = {
        "email": "new@example.test",
        "password": PASSWORD,
        "name": "New owner",
        "role": "prosumer",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 403
    result = client.post("/api/v1/auth/register", json=payload, headers=HEADERS)
    assert result.status_code == 201, result.text
    data = client.get("/api/v1/workspace").json()
    assert data["user"]["name"] == "New owner"
    assert len(data["readings"]) == 96
    assert (
        client.post(
            "/api/v1/auth/register", json={**payload, "role": "admin"}, headers=HEADERS
        ).status_code
        == 422
    )


def test_missing_readings_wait_then_explicit_replay_recovers(app):
    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    operator = client_for(app, "operator@urjasetu.demo")
    place(seller, "sell", price="4")
    place(buyer, "buy", price="6")
    operator.post("/api/v1/workspace/clear")
    operator.post("/api/v1/workspace/control", json={"action": "scenario", "scenario": "missing"})
    assert operator.post("/api/v1/workspace/control", json={"action": "deliver"}).status_code == 200
    pending = seller.get("/api/v1/workspace").json()
    assert pending["trades"][0]["status"] == "committed"
    assert pending["settlements"] == [] and pending["receipts"] == []
    result = operator.post("/api/v1/workspace/control", json={"action": "recover"})
    assert result.status_code == 200, result.text
    assert seller.get("/api/v1/workspace").json()["trades"][0]["status"] == "settled"
    operator.post("/api/v1/workspace/control", json={"action": "recover"})
    assert len(seller.get("/api/v1/workspace").json()["settlements"]) == 1


def test_cloudy_delivery_caps_payment_to_actual_energy(app):
    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    operator = client_for(app, "operator@urjasetu.demo")
    place(seller, "sell", "0.4", "4")
    place(buyer, "buy", "0.4", "6")
    operator.post("/api/v1/workspace/clear")
    operator.post("/api/v1/workspace/control", json={"action": "scenario", "scenario": "cloudy"})
    operator.post("/api/v1/workspace/control", json={"action": "deliver"})
    data = seller.get("/api/v1/workspace").json()
    delivered = Decimal(data["settlements"][0]["settled_kwh"])
    assert Decimal(0) < delivered < Decimal("0.4")
    assert Decimal(data["reconciliations"][0]["balancing_kwh"]) == Decimal("0.4") - delivered
    assert Decimal(data["settlements"][0]["gross_amount_inr"]) == (
        delivered * Decimal(data["prices"][0]["final_price"])
    ).quantize(Decimal("0.01"))


def test_multiple_trades_cannot_allocate_the_same_import_twice(app):
    seller = client_for(app, "asha@urjasetu.demo")
    buyer = client_for(app, "ravi@urjasetu.demo")
    operator = client_for(app, "operator@urjasetu.demo")
    for _ in range(2):
        place(seller, "sell", "0.35", "4")
        place(buyer, "buy", "0.35", "6")
    cleared = operator.post("/api/v1/workspace/clear")
    assert len(cleared.json()["trades"]) == 2
    operator.post("/api/v1/workspace/control", json={"action": "deliver"})
    with get_session_factory()() as db:
        allocations = list(db.scalars(select(TradeAllocation)))
        assert len(allocations) == 2
        reading = db.get(TelemetryReading, allocations[0].buyer_reading_id)
        assert allocations[1].buyer_reading_id == reading.id
        assert sum(a.energy_kwh for a in allocations) <= reading.grid_import_kwh
        assert sum(db.scalars(select(JournalEntry.amount_inr))) == 0


def test_concurrent_reservations_and_cancellation_release(app):
    clients = [client_for(app, "asha@urjasetu.demo") for _ in range(2)]
    clock = datetime.fromisoformat(
        clients[0].get("/api/v1/workspace").json()["simulation"]["clock"]
    ).astimezone(IST)
    start = (clock + timedelta(days=1)).replace(hour=12, minute=0)
    payload = {"side": "sell", "quantity": "0.7", "price": "4", "start": start.isoformat()}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda c: c.post("/api/v1/workspace/orders", json=payload), clients)
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    order = next(r.json() for r in results if r.status_code == 201)
    result = clients[0].post(f"/api/v1/workspace/orders/{order['id']}/cancel")
    assert result.status_code == 200, result.text
    assert clients[0].post("/api/v1/workspace/orders", json=payload).status_code == 201
    assert any(
        a["event_type"] == "order_cancelled"
        for a in clients[0].get("/api/v1/workspace").json()["audit"]
    )
