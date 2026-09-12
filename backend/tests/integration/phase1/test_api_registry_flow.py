"""Phase 1 acceptance gate: the registry workflow over HTTP.

docs/07_CODING_PHASES.md defines the Phase 1 gate as

    create user -> create site -> attach meter -> add PV -> verify -> eligibility

This module drives that end to end through the real API, then covers the
failure modes: ineligible users, malformed UUIDs, missing resources, duplicate
registrations, and the locked error envelope on every one of them.

Requests run inside the test's rolled-back transaction (see the `api_client`
fixture), so nothing leaks between tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Consent, User
from app.domain.enums import ConsentScope, UserRole, UserStatus

API = "/api/v1"
VERIFIED_AT = "2026-02-01T00:00:00Z"


def _discom_evidence(verification_type: str) -> dict[str, str]:
    """A DISCOM-issued, in-force verification record payload."""
    return {
        "verification_type": verification_type,
        "source": "discom",
        "verification_level": "discom_verified",
        "status": "verified",
        "verified_at": VERIFIED_AT,
    }


def _assert_error_envelope(response, *, code: str, status: int) -> dict:  # type: ignore[no-untyped-def]
    """Every non-2xx must match the envelope locked in docs/05_API_SPEC.md."""
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert error["request_id"]
    return error


# ---------------------------------------------------------------------------
# 1-7. The acceptance workflow
# ---------------------------------------------------------------------------


def test_phase_1_acceptance_workflow(api_client: TestClient, db_session: Session) -> None:
    """The full gate, ending in an eligible prosumer."""
    # 1. create user
    created = api_client.post(
        f"{API}/users",
        json={
            "display_name": "Asha Patel",
            "role": "prosumer",
            "email": f"asha-{uuid.uuid4().hex[:8]}@example.org",
            "status": "active",
        },
    )
    assert created.status_code == 201, created.text
    user = created.json()
    user_id = user["id"]
    assert user["role"] == "prosumer"

    # 2. create site
    site_response = api_client.post(
        f"{API}/sites",
        json={
            "owner_user_id": user_id,
            "name": "Ahmedabad Rooftop",
            "latitude": "23.022500",
            "longitude": "72.571400",
        },
    )
    assert site_response.status_code == 201, site_response.text
    site_id = site_response.json()["id"]
    assert site_response.json()["timezone"] == "Asia/Kolkata"

    # 3. attach meter
    meter_response = api_client.post(
        f"{API}/sites/{site_id}/meters",
        json={
            "meter_type": "net_meter",
            "vendor": "Secure Meters",
            "external_meter_ref": f"MTR-{uuid.uuid4().hex[:10]}",
        },
    )
    assert meter_response.status_code == 201, meter_response.text
    assert meter_response.json()["site_id"] == site_id

    # 4. attach PV asset
    asset_response = api_client.post(
        f"{API}/sites/{site_id}/energy-assets",
        json={"asset_type": "pv", "capacity_kw": "5.000", "status": "active"},
    )
    assert asset_response.status_code == 201, asset_response.text
    asset = asset_response.json()
    asset_id = asset["id"]
    # kW is serialised as a decimal string, not a float.
    assert asset["capacity_kw"] == "5.000"

    # 5. verify — the endpoint carries every kind of evidence, distinguished by
    #    `verification_type` (docs/04_DATA_MODEL.md entity 8).
    for evidence_type in ("utility_account", "meter", "energy_asset"):
        verification = api_client.post(
            f"{API}/assets/{asset_id}/verification", json=_discom_evidence(evidence_type)
        )
        assert verification.status_code == 201, verification.text
        # The owner is derived from the asset, never taken from the request.
        assert verification.json()["user_id"] == user_id
        assert verification.json()["asset_id"] == asset_id

    # Consents are not an API resource in Phase 1 — docs/05_API_SPEC.md defines
    # no endpoint for them — so the grants are seeded directly. See the Phase 1A
    # report: this is the one step of the gate that HTTP alone cannot perform.
    for scope in (ConsentScope.MARKET_PARTICIPATION, ConsentScope.METER_DATA):
        db_session.add(Consent(user_id=uuid.UUID(user_id), scope=scope))
    db_session.flush()

    # 6-7. request eligibility and confirm the eligible result
    eligibility = api_client.get(f"{API}/users/{user_id}/eligibility")
    assert eligibility.status_code == 200, eligibility.text
    decision = eligibility.json()

    assert decision["user_id"] == user_id
    assert decision["can_buy"] is True
    assert decision["can_sell"] is True
    assert decision["can_trade"] is True
    assert decision["trust_level"] == "discom_verified"
    assert decision["reasons"] == []
    assert decision["evaluated_at"]


def test_verification_raises_trust_level(api_client: TestClient) -> None:
    """Before verification the user is untrusted; after it, DISCOM-verified."""
    user_id = api_client.post(
        f"{API}/users", json={"display_name": "Ravi", "role": "prosumer", "status": "active"}
    ).json()["id"]
    site_id = api_client.post(
        f"{API}/sites", json={"owner_user_id": user_id, "name": "Roof"}
    ).json()["id"]
    asset_id = api_client.post(
        f"{API}/sites/{site_id}/energy-assets",
        json={"asset_type": "pv", "capacity_kw": "3.000", "status": "active"},
    ).json()["id"]

    before = api_client.get(f"{API}/users/{user_id}/eligibility").json()
    assert before["trust_level"] == "none"
    assert "UTILITY_ACCOUNT_NOT_DISCOM_VERIFIED" in before["reasons"]

    for evidence_type in ("utility_account", "meter"):
        api_client.post(
            f"{API}/assets/{asset_id}/verification", json=_discom_evidence(evidence_type)
        )

    after = api_client.get(f"{API}/users/{user_id}/eligibility").json()
    assert after["trust_level"] == "discom_verified"
    assert "UTILITY_ACCOUNT_NOT_DISCOM_VERIFIED" not in after["reasons"]


# ---------------------------------------------------------------------------
# 8. Ineligible cases
# ---------------------------------------------------------------------------


def test_brand_new_user_is_not_eligible(api_client: TestClient) -> None:
    user_id = api_client.post(
        f"{API}/users", json={"display_name": "Newcomer", "role": "consumer"}
    ).json()["id"]

    decision = api_client.get(f"{API}/users/{user_id}/eligibility").json()

    assert decision["can_trade"] is False
    assert decision["trust_level"] == "none"
    # Pending, unverified and without consent — every gate reports itself.
    assert "USER_NOT_ACTIVE" in decision["reasons"]
    assert "UTILITY_ACCOUNT_NOT_DISCOM_VERIFIED" in decision["reasons"]
    assert "MARKET_PARTICIPATION_CONSENT_MISSING" in decision["reasons"]


def test_suspended_user_cannot_trade(
    api_client: TestClient, make_user: Callable[..., User]
) -> None:
    user = make_user(status=UserStatus.SUSPENDED)

    decision = api_client.get(f"{API}/users/{user.id}/eligibility").json()

    assert decision["can_trade"] is False
    assert "USER_NOT_ACTIVE" in decision["reasons"]


def test_observer_role_cannot_trade(api_client: TestClient, make_user: Callable[..., User]) -> None:
    user = make_user(role=UserRole.REGULATOR_VIEWER, status=UserStatus.ACTIVE)

    decision = api_client.get(f"{API}/users/{user.id}/eligibility").json()

    assert decision["can_trade"] is False
    assert "ROLE_NOT_PERMITTED_TO_TRADE" in decision["reasons"]


def test_consumer_without_generation_cannot_sell(
    api_client: TestClient, db_session: Session
) -> None:
    user_id = api_client.post(
        f"{API}/users", json={"display_name": "Buyer", "role": "consumer", "status": "active"}
    ).json()["id"]
    site_id = api_client.post(
        f"{API}/sites", json={"owner_user_id": user_id, "name": "Flat"}
    ).json()["id"]
    asset_id = api_client.post(
        f"{API}/sites/{site_id}/energy-assets",
        json={"asset_type": "pv", "capacity_kw": "1.000", "status": "inactive"},
    ).json()["id"]
    for evidence_type in ("utility_account", "meter"):
        api_client.post(
            f"{API}/assets/{asset_id}/verification", json=_discom_evidence(evidence_type)
        )
    for scope in (ConsentScope.MARKET_PARTICIPATION, ConsentScope.METER_DATA):
        db_session.add(Consent(user_id=uuid.UUID(user_id), scope=scope))
    db_session.flush()

    decision = api_client.get(f"{API}/users/{user_id}/eligibility").json()

    assert decision["can_buy"] is True
    assert decision["can_sell"] is False
    assert "ROLE_NOT_PERMITTED_TO_SELL" in decision["reasons"]
    # The PV asset exists but is inactive, so it cannot back a sell order.
    assert "NO_ACTIVE_GENERATION_ASSET" in decision["reasons"]


def test_expired_verification_does_not_confer_trust(api_client: TestClient) -> None:
    """An expired record is history, not current trust."""
    user_id = api_client.post(
        f"{API}/users", json={"display_name": "Lapsed", "role": "prosumer", "status": "active"}
    ).json()["id"]
    site_id = api_client.post(
        f"{API}/sites", json={"owner_user_id": user_id, "name": "Roof"}
    ).json()["id"]
    asset_id = api_client.post(
        f"{API}/sites/{site_id}/energy-assets",
        json={"asset_type": "pv", "capacity_kw": "2.000", "status": "active"},
    ).json()["id"]

    api_client.post(
        f"{API}/assets/{asset_id}/verification",
        json={**_discom_evidence("utility_account"), "expires_at": "2026-03-01T00:00:00Z"},
    )

    decision = api_client.get(f"{API}/users/{user_id}/eligibility").json()

    assert decision["trust_level"] == "none"
    assert "UTILITY_ACCOUNT_NOT_DISCOM_VERIFIED" in decision["reasons"]


# ---------------------------------------------------------------------------
# 9. Invalid UUIDs
# ---------------------------------------------------------------------------


def test_invalid_uuid_in_path_is_rejected(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/users/not-a-uuid")

    error = _assert_error_envelope(response, code="REQUEST_VALIDATION_FAILED", status=422)
    assert error["details"]["errors"]


def test_invalid_uuid_on_eligibility_is_rejected(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/users/12345/eligibility")

    _assert_error_envelope(response, code="REQUEST_VALIDATION_FAILED", status=422)


def test_invalid_uuid_in_body_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(f"{API}/sites", json={"owner_user_id": "nope", "name": "Roof"})

    _assert_error_envelope(response, code="REQUEST_VALIDATION_FAILED", status=422)


def test_invalid_enum_value_is_rejected(api_client: TestClient) -> None:
    response = api_client.post(f"{API}/users", json={"display_name": "X", "role": "energy_baron"})

    _assert_error_envelope(response, code="REQUEST_VALIDATION_FAILED", status=422)


def test_non_positive_capacity_is_rejected(
    api_client: TestClient, make_site: Callable[..., object]
) -> None:
    site = make_site()

    response = api_client.post(
        f"{API}/sites/{site.id}/energy-assets",  # type: ignore[attr-defined]
        json={"asset_type": "pv", "capacity_kw": "0"},
    )

    _assert_error_envelope(response, code="REQUEST_VALIDATION_FAILED", status=422)


# ---------------------------------------------------------------------------
# 10. Missing resources
# ---------------------------------------------------------------------------


def test_missing_user_returns_404(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/users/{uuid.uuid4()}")

    _assert_error_envelope(response, code="USER_NOT_FOUND", status=404)


def test_missing_user_eligibility_returns_404(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/users/{uuid.uuid4()}/eligibility")

    _assert_error_envelope(response, code="USER_NOT_FOUND", status=404)


def test_site_for_unknown_owner_returns_404(api_client: TestClient) -> None:
    """A dangling owner is reported as a missing user, not a raw FK error."""
    response = api_client.post(
        f"{API}/sites", json={"owner_user_id": str(uuid.uuid4()), "name": "Ghost Roof"}
    )

    _assert_error_envelope(response, code="USER_NOT_FOUND", status=404)


def test_site_with_unknown_grid_node_returns_404(
    api_client: TestClient, make_user: Callable[..., User]
) -> None:
    user = make_user()

    response = api_client.post(
        f"{API}/sites",
        json={
            "owner_user_id": str(user.id),
            "name": "Unmapped",
            "grid_node_id": str(uuid.uuid4()),
        },
    )

    _assert_error_envelope(response, code="GRID_NODE_NOT_FOUND", status=404)


def test_missing_site_returns_404(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/sites/{uuid.uuid4()}")

    _assert_error_envelope(response, code="SITE_NOT_FOUND", status=404)


def test_meter_on_missing_site_returns_404(api_client: TestClient) -> None:
    response = api_client.post(
        f"{API}/sites/{uuid.uuid4()}/meters", json={"meter_type": "net_meter"}
    )

    _assert_error_envelope(response, code="SITE_NOT_FOUND", status=404)


def test_energy_asset_on_missing_site_returns_404(api_client: TestClient) -> None:
    response = api_client.post(
        f"{API}/sites/{uuid.uuid4()}/energy-assets",
        json={"asset_type": "pv", "capacity_kw": "3.000"},
    )

    _assert_error_envelope(response, code="SITE_NOT_FOUND", status=404)


def test_verification_on_missing_asset_returns_404(api_client: TestClient) -> None:
    response = api_client.post(
        f"{API}/assets/{uuid.uuid4()}/verification", json=_discom_evidence("energy_asset")
    )

    _assert_error_envelope(response, code="ENERGY_ASSET_NOT_FOUND", status=404)


def test_get_verification_for_missing_asset_returns_404(api_client: TestClient) -> None:
    response = api_client.get(f"{API}/assets/{uuid.uuid4()}/verification")

    _assert_error_envelope(response, code="ENERGY_ASSET_NOT_FOUND", status=404)


def test_inverter_for_missing_asset_returns_404(api_client: TestClient) -> None:
    response = api_client.post(f"{API}/inverters", json={"energy_asset_id": str(uuid.uuid4())})

    _assert_error_envelope(response, code="ENERGY_ASSET_NOT_FOUND", status=404)


# ---------------------------------------------------------------------------
# 11. Duplicate resources
# ---------------------------------------------------------------------------


def test_duplicate_email_returns_409(api_client: TestClient) -> None:
    email = f"dup-{uuid.uuid4().hex[:8]}@example.org"
    payload = {"display_name": "First", "role": "consumer", "email": email}
    assert api_client.post(f"{API}/users", json=payload).status_code == 201

    response = api_client.post(f"{API}/users", json={**payload, "display_name": "Second"})

    error = _assert_error_envelope(response, code="USER_EMAIL_ALREADY_EXISTS", status=409)
    assert error["details"]["email"] == email


def test_duplicate_meter_reference_returns_409(
    api_client: TestClient, make_site: Callable[..., object]
) -> None:
    """Two sites must not claim the same physical meter."""
    ref = f"MTR-{uuid.uuid4().hex[:10]}"
    first_site = make_site()
    second_site = make_site()
    body = {"meter_type": "net_meter", "external_meter_ref": ref}
    assert (
        api_client.post(f"{API}/sites/{first_site.id}/meters", json=body).status_code == 201  # type: ignore[attr-defined]
    )

    response = api_client.post(f"{API}/sites/{second_site.id}/meters", json=body)  # type: ignore[attr-defined]

    _assert_error_envelope(response, code="METER_REF_ALREADY_REGISTERED", status=409)


def test_duplicate_inverter_reference_returns_409(
    api_client: TestClient, make_energy_asset: Callable[..., object]
) -> None:
    ref = f"INV-{uuid.uuid4().hex[:10]}"
    asset = make_energy_asset()
    body = {"energy_asset_id": str(asset.id), "external_device_ref": ref}  # type: ignore[attr-defined]
    assert api_client.post(f"{API}/inverters", json=body).status_code == 201

    response = api_client.post(f"{API}/inverters", json=body)

    _assert_error_envelope(response, code="INVERTER_REF_ALREADY_REGISTERED", status=409)


def test_inconsistent_verification_is_rejected(
    api_client: TestClient, make_energy_asset: Callable[..., object]
) -> None:
    """Database check constraints surface as a domain conflict, not a 500."""
    asset = make_energy_asset()

    response = api_client.post(
        f"{API}/assets/{asset.id}/verification",  # type: ignore[attr-defined]
        json={
            "verification_type": "energy_asset",
            "source": "discom",
            "verification_level": "discom_verified",
            "status": "verified",
            "verified_at": None,
        },
    )

    _assert_error_envelope(response, code="VERIFICATION_RECORD_INVALID", status=409)


# ---------------------------------------------------------------------------
# 12. Remaining endpoints and envelope coverage
# ---------------------------------------------------------------------------


def test_get_site_returns_its_registry(api_client: TestClient) -> None:
    user_id = api_client.post(
        f"{API}/users", json={"display_name": "Owner", "role": "prosumer"}
    ).json()["id"]
    site_id = api_client.post(
        f"{API}/sites", json={"owner_user_id": user_id, "name": "Detail Roof"}
    ).json()["id"]
    api_client.post(f"{API}/sites/{site_id}/meters", json={"meter_type": "smart_meter"})
    api_client.post(
        f"{API}/sites/{site_id}/energy-assets",
        json={"asset_type": "pv", "capacity_kw": "4.000"},
    )

    detail = api_client.get(f"{API}/sites/{site_id}").json()

    assert len(detail["meters"]) == 1
    assert len(detail["energy_assets"]) == 1


def test_patch_user_updates_profile(api_client: TestClient) -> None:
    user_id = api_client.post(
        f"{API}/users", json={"display_name": "Before", "role": "consumer"}
    ).json()["id"]

    response = api_client.patch(
        f"{API}/users/{user_id}", json={"display_name": "After", "status": "active"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "After"
    assert response.json()["status"] == "active"
    # Untouched fields survive a partial update.
    assert response.json()["role"] == "consumer"


def test_patch_missing_user_returns_404(api_client: TestClient) -> None:
    response = api_client.patch(f"{API}/users/{uuid.uuid4()}", json={"display_name": "X"})

    _assert_error_envelope(response, code="USER_NOT_FOUND", status=404)


def test_register_inverter(
    api_client: TestClient, make_energy_asset: Callable[..., object]
) -> None:
    asset = make_energy_asset()

    response = api_client.post(
        f"{API}/inverters",
        json={
            "energy_asset_id": str(asset.id),  # type: ignore[attr-defined]
            "manufacturer": "Delta",
            "model": "RPI-M6A",
            "protocol": "sunspec_modbus_tcp",
            "adapter_type": "simulator_adapter",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["protocol"] == "sunspec_modbus_tcp"


def test_request_id_is_echoed_on_errors(api_client: TestClient) -> None:
    supplied = "phase-1a-trace-0001"

    response = api_client.get(f"{API}/users/{uuid.uuid4()}", headers={"X-Request-ID": supplied})

    assert response.headers["X-Request-ID"] == supplied
    assert response.json()["error"]["request_id"] == supplied


def test_endpoints_are_documented_in_openapi(api_client: TestClient) -> None:
    """Every Phase 1 path from docs/05_API_SPEC.md is published."""
    paths = api_client.get("/openapi.json").json()["paths"]

    for path in (
        f"{API}/users",
        f"{API}/users/{{user_id}}",
        f"{API}/users/{{user_id}}/eligibility",
        f"{API}/sites",
        f"{API}/sites/{{site_id}}",
        f"{API}/sites/{{site_id}}/meters",
        f"{API}/sites/{{site_id}}/energy-assets",
        f"{API}/assets/{{asset_id}}/verification",
        f"{API}/inverters",
    ):
        assert path in paths, f"{path} missing from OpenAPI"
