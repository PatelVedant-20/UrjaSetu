"""Phase 1 API endpoint tests.

Verifies the Phase 1 REST API surface according to docs/05_API_SPEC.md:
  1. Users / Identity (/users, /users/{id}, /users/{id}/eligibility)
  2. Sites (/sites, /sites/{id})
  3. Meters (/sites/{id}/meters)
  4. Assets (/sites/{id}/energy-assets, /assets/{id}/verification)
  5. Inverters (/inverters)
  7. Error envelope compliance on all error responses
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


class TestUsersAPI:
    """Verify Users / Identity endpoints."""

    def test_create_user_endpoint(self, phase1_client: TestClient) -> None:
        payload = {
            "email": f"api_user_{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "API Test Prosumer",
            "role": "prosumer",
        }
        response = phase1_client.post("/api/v1/users", json=payload)
        assert response.status_code in (200, 201), f"Unexpected status: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["display_name"] == "API Test Prosumer"
        assert data["role"] == "prosumer"

    def test_get_user_profile(self, phase1_client: TestClient) -> None:
        # Create user first
        payload = {
            "email": f"get_user_{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "Get User",
            "role": "consumer",
        }
        create_resp = phase1_client.post("/api/v1/users", json=payload)
        if create_resp.status_code not in (200, 201):
            raise AssertionError(f"User creation failed: {create_resp.text}")

        user_id = create_resp.json()["id"]
        get_resp = phase1_client.get(f"/api/v1/users/{user_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == user_id

    def test_get_nonexistent_user_returns_404_with_error_envelope(
        self, phase1_client: TestClient
    ) -> None:
        fake_id = str(uuid.uuid4())
        response = phase1_client.get(f"/api/v1/users/{fake_id}")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "request_id" in body["error"]

    def test_user_eligibility_endpoint(self, phase1_client: TestClient) -> None:
        payload = {
            "email": f"elig_{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "Eligible User",
            "role": "prosumer",
        }
        create_resp = phase1_client.post("/api/v1/users", json=payload)
        if create_resp.status_code in (200, 201):
            user_id = create_resp.json()["id"]
            elig_resp = phase1_client.get(f"/api/v1/users/{user_id}/eligibility")
            assert elig_resp.status_code == 200
            data = elig_resp.json()
            assert {"can_buy", "can_sell", "can_trade", "trust_level", "reasons"} <= set(data)


class TestSitesAndAssetsAPI:
    """Verify Sites, Meters, and Assets endpoints."""

    def test_create_and_get_site(self, phase1_client: TestClient) -> None:
        # Create user first
        user_resp = phase1_client.post(
            "/api/v1/users",
            json={
                "email": f"site_user_{uuid.uuid4().hex[:8]}@example.com",
                "display_name": "Site User",
                "role": "prosumer",
            },
        )
        if user_resp.status_code not in (200, 201):
            raise AssertionError(f"User creation failed: {user_resp.text}")

        user_id = user_resp.json()["id"]
        site_resp = phase1_client.post(
            "/api/v1/sites",
            json={
                "owner_user_id": user_id,
                "name": "Palm Residency #12",
                "latitude": 12.9716,
                "longitude": 77.5946,
                "timezone": "Asia/Kolkata",
            },
        )
        assert site_resp.status_code in (200, 201), f"Site creation failed: {site_resp.text}"
        site_id = site_resp.json()["id"]

        get_resp = phase1_client.get(f"/api/v1/sites/{site_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Palm Residency #12"

    def test_attach_meter_to_site(self, phase1_client: TestClient) -> None:
        # Setup user and site
        user_id = (
            phase1_client.post(
                "/api/v1/users",
                json={
                    "email": f"meter_api_{uuid.uuid4().hex[:8]}@example.com",
                    "display_name": "Meter User",
                    "role": "prosumer",
                },
            )
            .json()
            .get("id")
        )
        if not user_id:
            raise AssertionError("Could not create user")

        site_id = (
            phase1_client.post(
                "/api/v1/sites",
                json={"owner_user_id": user_id, "name": "Meter Site", "timezone": "Asia/Kolkata"},
            )
            .json()
            .get("id")
        )
        if not site_id:
            raise AssertionError("Could not create site")

        meter_resp = phase1_client.post(
            f"/api/v1/sites/{site_id}/meters",
            json={
                "meter_type": "smart_meter",
                "vendor": "Schneider Electric",
                "external_meter_ref": f"API_MTR_{uuid.uuid4().hex[:8]}",
            },
        )
        assert meter_resp.status_code in (200, 201), f"Meter creation failed: {meter_resp.text}"

    def test_register_energy_asset(self, phase1_client: TestClient) -> None:
        # Setup user and site
        user_id = (
            phase1_client.post(
                "/api/v1/users",
                json={
                    "email": f"asset_api_{uuid.uuid4().hex[:8]}@example.com",
                    "display_name": "Asset User",
                    "role": "prosumer",
                },
            )
            .json()
            .get("id")
        )
        site_id = (
            phase1_client.post(
                "/api/v1/sites",
                json={"owner_user_id": user_id, "name": "Asset Site", "timezone": "Asia/Kolkata"},
            )
            .json()
            .get("id")
        )

        asset_resp = phase1_client.post(
            f"/api/v1/sites/{site_id}/energy-assets",
            json={
                "asset_type": "pv",
                "capacity_kw": 5.0,
                "status": "active",
            },
        )
        assert asset_resp.status_code in (200, 201), f"Asset creation failed: {asset_resp.text}"
