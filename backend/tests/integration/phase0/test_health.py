"""Phase 0 gate: the API starts and its health surface behaves.

Covers docs/09_PHASE_0_SETUP.md Step 5/Step 9 and the endpoints locked in
docs/05_API_SPEC.md.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "UrjaSetu"
    assert body["version"]
    assert body["environment"]


def test_health_does_not_require_the_database(client: TestClient) -> None:
    """Liveness must be pure.

    If `/health` touched PostgreSQL, a database blip would look like a dead
    process and an orchestrator would restart the API pointlessly.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert "dependencies" not in response.json()


def test_readiness_reports_postgresql(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"

    dependencies = {dep["name"]: dep for dep in body["dependencies"]}
    assert "postgresql" in dependencies
    assert dependencies["postgresql"]["status"] == "ok"
    # Proves a real round-trip query ran, not a socket check.
    assert dependencies["postgresql"]["latency_ms"] is not None


def test_meta_reports_locked_market_mode(client: TestClient) -> None:
    response = client.get("/api/v1/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["api_version"] == "v1"
    # Day-ahead is locked in docs/00_PROJECT_BIBLE.md section 7.
    assert body["market_mode"] == "day_ahead"
    # Phase 0 wires no external adapters.
    assert body["enabled_integrations"] == []


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    """Every non-2xx response matches the envelope in docs/05_API_SPEC.md."""
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"]


def test_request_id_is_echoed_when_supplied(client: TestClient) -> None:
    """An inbound correlation id survives into the response and the envelope."""
    supplied = "11111111-2222-3333-4444-555555555555"

    response = client.get("/api/v1/does-not-exist", headers={"X-Request-ID": supplied})

    assert response.headers["X-Request-ID"] == supplied
    assert response.json()["error"]["request_id"] == supplied


def test_openapi_is_available_in_development(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/api/v1/meta" in paths
