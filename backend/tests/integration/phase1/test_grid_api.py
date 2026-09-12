"""Integration tests for Phase-1 Grid Nodes read-only REST API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models.grid import GridNode


def test_list_grid_nodes_empty(phase1_client: TestClient) -> None:
    resp = phase1_client.get("/api/v1/grid/nodes")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


def test_list_grid_nodes_with_data(phase1_client: TestClient, db_session: Session) -> None:
    # Seed a test node
    node = GridNode(
        external_ref="FEEDER-TEST-01",
        node_type="feeder",
        nominal_voltage_kv=11.0,
        feeder_id="FDR-TEST",
    )
    db_session.add(node)
    db_session.flush()

    resp = phase1_client.get("/api/v1/grid/nodes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    refs = [n["external_ref"] for n in data["items"]]
    assert "FEEDER-TEST-01" in refs
