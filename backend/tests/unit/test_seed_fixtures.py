"""tests/unit/test_seed_fixtures.py — Phase-1 seed fixture validation.

Validates the JSON fixture files in data/synthetic/ for:
  - correct JSON structure
  - required fields per entity type
  - deterministic UUIDs
  - no real-looking PII
  - referential integrity between fixtures
  - no telemetry/forecast/order/trade data (Phase 0/1 scope only)

Does NOT require a database. Runs with:
    pytest backend/tests/unit/test_seed_fixtures.py -v
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"

FIXTURE_FILES = [
    "grid_nodes",
    "users",
    "utility_accounts",
    "sites",
    "meters",
    "energy_assets",
    "inverter_devices",
    "verification_records",
    "consents",
]

# Fields forbidden in Phase 0/1 seed (no telemetry, forecasts, orders, trades)
FORBIDDEN_KEYS = {
    "generation_kw",
    "load_kw",
    "grid_import_kw",
    "grid_export_kw",
    "predicted_kw",
    "clearing_price_inr_per_kwh",
    "energy_kwh",
    "market_session_id",
    "forecast_run_id",
    "buy_order_id",
    "sell_order_id",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_fixture(name: str) -> dict:
    path = SYNTHETIC_DIR / f"{name}.json"
    assert path.exists(), f"Fixture file missing: {path}"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


def is_demo_uuid(value: str) -> bool:
    """Seed UUIDs must start with known demo prefixes (10…, 20…, … 90…)."""
    demo_prefixes = (
        "10000000-",
        "20000000-",
        "30000000-",
        "40000000-",
        "50000000-",
        "60000000-",
        "70000000-",
        "80000000-",
        "90000000-",
    )
    return any(str(value).startswith(p) for p in demo_prefixes)


# ---------------------------------------------------------------------------
# Tests — file presence and structure
# ---------------------------------------------------------------------------
class TestFixtureFilesExist:
    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_fixture_file_exists(self, name: str) -> None:
        path = SYNTHETIC_DIR / f"{name}.json"
        assert path.exists(), f"Missing fixture: {path}"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_fixture_has_comment(self, name: str) -> None:
        data = load_fixture(name)
        assert "_comment" in data, f"{name}.json missing _comment field"
        assert "DEMO" in data["_comment"], f"{name}.json _comment must include 'DEMO'"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_fixture_has_seed_version(self, name: str) -> None:
        data = load_fixture(name)
        assert "_seed_version" in data, f"{name}.json missing _seed_version"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_fixture_has_records_list(self, name: str) -> None:
        data = load_fixture(name)
        assert name in data, f"{name}.json must have top-level key '{name}'"
        assert isinstance(data[name], list), f"{name} must be a list"
        assert len(data[name]) > 0, f"{name} must contain at least one record"


# ---------------------------------------------------------------------------
# Tests — ID conventions
# ---------------------------------------------------------------------------
class TestIDConventions:
    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_all_ids_are_valid_uuids(self, name: str) -> None:
        records = load_fixture(name)[name]
        for r in records:
            assert "id" in r, f"{name} record missing 'id'"
            assert is_valid_uuid(r["id"]), f"Invalid UUID in {name}: {r['id']}"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_all_ids_are_demo_prefixed(self, name: str) -> None:
        records = load_fixture(name)[name]
        for r in records:
            assert is_demo_uuid(r["id"]), (
                f"{name} record id {r['id']} does not start with a demo prefix. "
                "Seed UUIDs must use well-known prefixes to distinguish from production data."
            )

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_ids_are_unique_within_fixture(self, name: str) -> None:
        records = load_fixture(name)[name]
        ids = [r["id"] for r in records]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found in {name}"


# ---------------------------------------------------------------------------
# Tests — no real PII
# ---------------------------------------------------------------------------
class TestNoPII:
    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_emails_are_demo_domain(self, name: str) -> None:
        records = load_fixture(name)[name]
        for r in records:
            if "email" in r and r["email"]:
                assert r["email"].endswith(
                    ".demo"
                ), f"email {r['email']} in {name} must end with .demo"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_no_real_consumer_numbers(self, name: str) -> None:
        records = load_fixture(name)[name]
        real_cn_pattern = re.compile(r"^\d{10,}$")
        for r in records:
            cn = r.get("consumer_number_hash", "")
            if cn:
                assert not real_cn_pattern.match(
                    cn
                ), f"consumer_number_hash {cn!r} looks like a real consumer number"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_no_real_meter_serials(self, name: str) -> None:
        records = load_fixture(name)[name]
        for r in records:
            ref = r.get("external_meter_ref", "")
            if ref:
                assert ref.startswith(
                    "DEMO-"
                ), f"external_meter_ref {ref!r} in {name} must start with DEMO-"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_no_phone_numbers(self, name: str) -> None:
        phone_pattern = re.compile(r"\b[6-9]\d{9}\b")  # Indian mobile numbers
        for r in load_fixture(name)[name]:
            for v in r.values():
                if isinstance(v, str):
                    assert not phone_pattern.search(
                        v
                    ), f"Possible phone number found in {name}: {v!r}"


# ---------------------------------------------------------------------------
# Tests — Phase scope (no telemetry/order/trade data)
# ---------------------------------------------------------------------------
class TestPhaseScope:
    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_no_forbidden_keys(self, name: str) -> None:
        records = load_fixture(name)[name]
        for r in records:
            forbidden = set(r.keys()) & FORBIDDEN_KEYS
            assert not forbidden, f"{name} record contains forbidden Phase 2+ keys: {forbidden}"


# ---------------------------------------------------------------------------
# Tests — referential integrity
# ---------------------------------------------------------------------------
class TestReferentialIntegrity:
    def _ids(self, name: str) -> set[str]:
        return {r["id"] for r in load_fixture(name)[name]}

    def test_utility_accounts_reference_valid_users(self) -> None:
        user_ids = self._ids("users")
        for r in load_fixture("utility_accounts")["utility_accounts"]:
            assert (
                r["user_id"] in user_ids
            ), f"utility_account {r['id']} references unknown user_id {r['user_id']}"

    def test_sites_reference_valid_users(self) -> None:
        user_ids = self._ids("users")
        for r in load_fixture("sites")["sites"]:
            assert (
                r["owner_user_id"] in user_ids
            ), f"site {r['id']} references unknown owner_user_id {r['owner_user_id']}"

    def test_sites_reference_valid_grid_nodes(self) -> None:
        node_ids = self._ids("grid_nodes")
        for r in load_fixture("sites")["sites"]:
            assert (
                r["grid_node_id"] in node_ids
            ), f"site {r['id']} references unknown grid_node_id {r['grid_node_id']}"

    def test_meters_reference_valid_sites(self) -> None:
        site_ids = self._ids("sites")
        for r in load_fixture("meters")["meters"]:
            assert (
                r["site_id"] in site_ids
            ), f"meter {r['id']} references unknown site_id {r['site_id']}"

    def test_energy_assets_reference_valid_sites(self) -> None:
        site_ids = self._ids("sites")
        for r in load_fixture("energy_assets")["energy_assets"]:
            assert (
                r["site_id"] in site_ids
            ), f"energy_asset {r['id']} references unknown site_id {r['site_id']}"

    def test_inverter_devices_reference_valid_assets(self) -> None:
        asset_ids = self._ids("energy_assets")
        for r in load_fixture("inverter_devices")["inverter_devices"]:
            assert (
                r["energy_asset_id"] in asset_ids
            ), f"inverter {r['id']} references unknown energy_asset_id {r['energy_asset_id']}"

    def test_verification_records_reference_valid_users(self) -> None:
        user_ids = self._ids("users")
        for r in load_fixture("verification_records")["verification_records"]:
            assert (
                r["user_id"] in user_ids
            ), f"verification_record {r['id']} references unknown user_id {r['user_id']}"

    def test_verification_records_asset_refs_valid(self) -> None:
        asset_ids = self._ids("energy_assets")
        for r in load_fixture("verification_records")["verification_records"]:
            aid = r.get("asset_id")
            if aid is not None:
                assert (
                    aid in asset_ids
                ), f"verification_record {r['id']} references unknown asset_id {aid}"

    def test_consents_reference_valid_users(self) -> None:
        user_ids = self._ids("users")
        for r in load_fixture("consents")["consents"]:
            assert (
                r["user_id"] in user_ids
            ), f"consent {r['id']} references unknown user_id {r['user_id']}"


# ---------------------------------------------------------------------------
# Tests — seed determinism
# ---------------------------------------------------------------------------
class TestDeterminism:
    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_fixture_loads_same_data_twice(self, name: str) -> None:
        first = load_fixture(name)
        second = load_fixture(name)
        assert first == second, f"{name} fixture returned different data on second load"

    @pytest.mark.parametrize("name", FIXTURE_FILES)
    def test_fixture_ids_are_stable(self, name: str) -> None:
        """IDs must be hardcoded, not generated at load time."""
        ids_first = [r["id"] for r in load_fixture(name)[name]]
        ids_second = [r["id"] for r in load_fixture(name)[name]]
        assert ids_first == ids_second
