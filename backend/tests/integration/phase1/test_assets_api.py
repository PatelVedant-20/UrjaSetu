"""Integration tests for Phase-1 Assets / Sites / Verification REST API."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _create_user(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/users",
        json={
            "email": f"owner_{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "Asset Owner",
            "role": "prosumer",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_site_lifecycle(phase1_client: TestClient) -> None:
    owner_id = _create_user(phase1_client)

    # 1. Create site
    site_payload = {
        "owner_user_id": owner_id,
        "name": "Community Solar Plant Alpha",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "timezone": "Asia/Kolkata",
    }
    create_resp = phase1_client.post("/api/v1/sites", json=site_payload)
    assert create_resp.status_code == 201, create_resp.text
    site_data = create_resp.json()
    site_id = site_data["id"]
    assert site_data["name"] == "Community Solar Plant Alpha"

    # 2. Get site
    get_resp = phase1_client.get(f"/api/v1/sites/{site_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == site_id

    # 3. Attach meter
    meter_payload = {
        "meter_type": "smart_meter",
        "vendor": "Schneider Electric",
        "external_meter_ref": f"MTR-{uuid.uuid4().hex[:6]}",
        "verification_level": "self_declared",
        "active": True,
    }
    meter_resp = phase1_client.post(f"/api/v1/sites/{site_id}/meters", json=meter_payload)
    assert meter_resp.status_code == 201
    meter_data = meter_resp.json()
    assert meter_data["site_id"] == site_id
    assert meter_data["meter_type"] == "smart_meter"

    # 4. Register energy asset (PV)
    asset_payload = {
        "asset_type": "pv",
        "capacity_kw": 25.5,
        "status": "planned",
    }
    asset_resp = phase1_client.post(f"/api/v1/sites/{site_id}/energy-assets", json=asset_payload)
    assert asset_resp.status_code == 201
    asset_data = asset_resp.json()
    asset_id = asset_data["id"]
    assert asset_data["site_id"] == site_id
    assert asset_data["capacity_kw"] == "25.500"

    # 5. Submit verification record for asset
    verif_payload = {
        "verification_type": "energy_asset",
        "source": "discom",
        "verification_level": "discom_verified",
        "status": "verified",
        "verified_at": "2026-02-01T00:00:00Z",
    }
    verif_resp = phase1_client.post(f"/api/v1/assets/{asset_id}/verification", json=verif_payload)
    assert verif_resp.status_code == 201
    verif_data = verif_resp.json()
    assert verif_data["asset_id"] == asset_id
    assert verif_data["status"] == "verified"

    # 6. Retrieve verification record
    get_verif_resp = phase1_client.get(f"/api/v1/assets/{asset_id}/verification")
    assert get_verif_resp.status_code == 200
    assert get_verif_resp.json()[0]["asset_id"] == asset_id

    # 7. Register inverter
    inverter_payload = {
        "energy_asset_id": asset_id,
        "manufacturer": "SMA Solar",
        "model": "Sunny Tripower 25000TL",
        "protocol": "sunspec_modbus_tcp",
        "external_device_ref": f"INV-{uuid.uuid4().hex[:6]}",
        "adapter_type": "sma_sunspec",
    }
    inv_resp = phase1_client.post("/api/v1/inverters", json=inverter_payload)
    assert inv_resp.status_code == 201
    inv_data = inv_resp.json()
    assert inv_data["energy_asset_id"] == asset_id
    assert inv_data["manufacturer"] == "SMA Solar"
