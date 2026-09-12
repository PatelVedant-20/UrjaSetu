"""Integration tests for Phase-1 Users / Identity REST API."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_create_user_success(phase1_client: TestClient) -> None:
    payload = {
        "email": f"alice_{uuid.uuid4().hex[:8]}@example.com",
        "display_name": "Alice Sharma",
        "role": "consumer",
    }
    resp = phase1_client.post("/api/v1/users", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["display_name"] == "Alice Sharma"
    assert data["role"] == "consumer"
    assert data["status"] == "pending"
    assert "id" in data


def test_create_user_duplicate_email_conflict(phase1_client: TestClient) -> None:
    email = f"bob_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": email,
        "display_name": "Bob Prosumer",
        "role": "prosumer",
    }
    resp1 = phase1_client.post("/api/v1/users", json=payload)
    assert resp1.status_code == 201

    resp2 = phase1_client.post("/api/v1/users", json=payload)
    assert resp2.status_code == 409
    err = resp2.json()
    assert "error" in err
    assert err["error"]["code"] == "USER_EMAIL_ALREADY_EXISTS"
    assert "request_id" in err["error"]


def test_get_user_success(phase1_client: TestClient) -> None:
    payload = {
        "email": f"carol_{uuid.uuid4().hex[:8]}@example.com",
        "display_name": "Carol Patel",
        "role": "prosumer",
    }
    create_resp = phase1_client.post("/api/v1/users", json=payload)
    user_id = create_resp.json()["id"]

    get_resp = phase1_client.get(f"/api/v1/users/{user_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == user_id
    assert get_resp.json()["display_name"] == "Carol Patel"


def test_get_user_not_found(phase1_client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    resp = phase1_client.get(f"/api/v1/users/{fake_id}")
    assert resp.status_code == 404
    err = resp.json()
    assert err["error"]["code"] == "USER_NOT_FOUND"


def test_update_user_display_name(phase1_client: TestClient) -> None:
    payload = {
        "email": f"dan_{uuid.uuid4().hex[:8]}@example.com",
        "display_name": "Dan Original",
        "role": "consumer",
    }
    create_resp = phase1_client.post("/api/v1/users", json=payload)
    user_id = create_resp.json()["id"]

    patch_resp = phase1_client.patch(
        f"/api/v1/users/{user_id}",
        json={"display_name": "Dan Updated"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["display_name"] == "Dan Updated"


def test_get_user_eligibility(phase1_client: TestClient) -> None:
    payload = {
        "email": f"eve_{uuid.uuid4().hex[:8]}@example.com",
        "display_name": "Eve Prosumer",
        "role": "prosumer",
    }
    create_resp = phase1_client.post("/api/v1/users", json=payload)
    user_id = create_resp.json()["id"]

    elig_resp = phase1_client.get(f"/api/v1/users/{user_id}/eligibility")
    assert elig_resp.status_code == 200
    data = elig_resp.json()
    assert data["user_id"] == user_id
    assert data["can_trade"] is False
    assert data["trust_level"] == "none"
    assert "UTILITY_ACCOUNT_NOT_DISCOM_VERIFIED" in data["reasons"]
    assert "MARKET_PARTICIPATION_CONSENT_MISSING" in data["reasons"]
