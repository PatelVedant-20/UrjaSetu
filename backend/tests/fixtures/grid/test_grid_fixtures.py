"""Unit and contract integration tests for Phase 5 Grid Scenarios & Fixtures."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import pytest

from app.domain.enums import (
    GridNodeType,
    GridValidationDecision,
    GridValidationStatus,
    GridViolationType,
)
from app.domain.interfaces.grid import (
    GridEngine,
    GridValidationRequest,
    GridValidationResult,
    GridViolation,
    NetworkModel,
)
from app.domain.policies.grid_limits import (
    decide,
    effective_status,
    resolve_status,
)
from tests.fixtures.grid.loader import (
    build_canonical_network_model,
    build_canonical_validation_request,
    get_expected_decision,
    get_expected_validation_result,
    get_grid_fixtures_dir,
    load_grid_fixture,
    load_grid_manifest,
)
from tests.integration.phase5.conftest import FailingGridEngine, StubGridEngine

REQUIRED_SCENARIOS = [
    "healthy_radial_feeder",
    "rated_line_below_current_flow",
    "rated_transformer_below_current_flow",
    "voltage_violation",
    "line_overload",
    "transformer_overload",
    "multiple_simultaneous_violations",
    "unrated_edge_unknown_validation",
    "solver_failure_unknown",
    "safe_proposed_trade",
    "unsafe_proposed_trade",
]


class TestGridManifestAndSchemas:
    """Validate manifest and JSON schemas for all 11 grid scenarios."""

    def test_manifest_contains_all_11_scenarios(self) -> None:
        manifest = load_grid_manifest()
        scenarios = manifest.get("scenarios", {})
        for req in REQUIRED_SCENARIOS:
            assert req in scenarios, f"Manifest missing required scenario: {req}"

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_scenario_json_structure(self, scenario_name: str) -> None:
        data = load_grid_fixture(scenario_name)

        assert "scenario_id" in data
        assert "title" in data
        assert "topology" in data
        assert "limits" in data
        assert "expected_validation" in data

        top = data["topology"]
        assert "version" in top
        assert "nodes" in top
        assert len(top["nodes"]) >= 2

        limits = data["limits"]
        assert "min_voltage_pu" in limits
        assert "max_voltage_pu" in limits
        assert "max_line_loading_pct" in limits
        assert "max_transformer_loading_pct" in limits

        exp = data["expected_validation"]
        assert exp["status"] in ("safe", "unsafe", "unknown")
        assert exp["decision"] in ("accept", "reject")

    def test_referential_integrity_against_synthetic_seed(self) -> None:
        fixtures_dir = get_grid_fixtures_dir()
        seed_file = fixtures_dir.parent / "grid_nodes.json"

        with open(seed_file, encoding="utf-8") as f:
            seed_data = json.load(f)
        canonical_node_ids = {n["id"] for n in seed_data["grid_nodes"]}

        for sc_name in REQUIRED_SCENARIOS:
            data = load_grid_fixture(sc_name)
            for node in data["topology"]["nodes"]:
                assert (
                    node["id"] in canonical_node_ids
                ), f"Node {node['id']} in {sc_name} not found in grid_nodes.json"


class TestCanonicalModelLoading:
    """Validate projection into canonical NetworkModel and GridValidationRequest dataclasses."""

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_build_canonical_network_model(self, scenario_name: str) -> None:
        network = build_canonical_network_model(scenario_name)

        assert isinstance(network, NetworkModel)
        assert len(network.nodes) >= 2
        assert len(network.lines) >= 1
        assert len(network.transformers) >= 1

        for node in network.nodes:
            assert isinstance(node.node_id, UUID)
            assert isinstance(node.node_type, GridNodeType)
            assert node.nominal_voltage_kv > Decimal("0")

        # In scenario 8 (unrated edge), exactly one element has rating_kw = None
        if scenario_name == "unrated_edge_unknown_validation":
            assert len(network.unrated_elements) == 1
            assert network.has_complete_ratings is False
        else:
            assert network.has_complete_ratings is True

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_build_canonical_validation_request(self, scenario_name: str) -> None:
        request = build_canonical_validation_request(scenario_name)

        assert isinstance(request, GridValidationRequest)
        assert request.interval.total_seconds() > 0
        assert request.limits.min_voltage_pu < request.limits.max_voltage_pu
        assert request.limits.max_line_loading_pct > Decimal("0")

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_get_expected_validation_result(self, scenario_name: str) -> None:
        result = get_expected_validation_result(scenario_name)

        assert isinstance(result, GridValidationResult)
        assert isinstance(result.status, GridValidationStatus)
        for v in result.violations:
            assert isinstance(v, GridViolation)
            assert isinstance(v.violation_type, GridViolationType)
            assert v.observed > Decimal("0")
            assert v.limit > Decimal("0")


class TestDomainPolicyDecisions:
    """Validate policy rules (resolve_status, effective_status, decide) match expected decisions."""

    @pytest.mark.parametrize("scenario_name", REQUIRED_SCENARIOS)
    def test_scenario_policy_evaluation(self, scenario_name: str) -> None:
        request = build_canonical_validation_request(scenario_name)
        result = get_expected_validation_result(scenario_name)
        expected_decision = get_expected_decision(scenario_name)

        # 1. Reconcile reported status with network completeness
        status = resolve_status(result.status, unrated_elements=request.network.unrated_elements)

        # 2. Account for violations caused by proposed trade
        final_status = effective_status(status, caused_violations=result.caused_violations)

        # 3. Form final trade decision
        decision = decide(status=final_status, caused_violations=result.caused_violations)

        assert decision == expected_decision


class TestSpecificScenarioSemantics:
    """Detailed verification of specific scenario edge cases."""

    def test_01_healthy_radial_feeder(self) -> None:
        result = get_expected_validation_result("healthy_radial_feeder")
        assert result.status is GridValidationStatus.SAFE
        assert result.safe is True
        assert len(result.violations) == 0
        assert get_expected_decision("healthy_radial_feeder") is GridValidationDecision.ACCEPT

    def test_02_rated_line_below_current_flow(self) -> None:
        result = get_expected_validation_result("rated_line_below_current_flow")
        assert result.status is GridValidationStatus.UNSAFE
        assert any(v.violation_type is GridViolationType.LINE_OVERLOAD for v in result.violations)
        decision = get_expected_decision("rated_line_below_current_flow")
        assert decision is GridValidationDecision.REJECT

    def test_03_rated_transformer_below_current_flow(self) -> None:
        result = get_expected_validation_result("rated_transformer_below_current_flow")
        assert result.status is GridValidationStatus.UNSAFE
        assert any(
            v.violation_type is GridViolationType.TRANSFORMER_OVERLOAD for v in result.violations
        )
        decision = get_expected_decision("rated_transformer_below_current_flow")
        assert decision is GridValidationDecision.REJECT

    def test_04_voltage_violation(self) -> None:
        result = get_expected_validation_result("voltage_violation")
        assert result.status is GridValidationStatus.UNSAFE
        assert any(v.violation_type is GridViolationType.OVER_VOLTAGE for v in result.violations)
        assert get_expected_decision("voltage_violation") is GridValidationDecision.REJECT

    def test_07_multiple_simultaneous_violations(self) -> None:
        result = get_expected_validation_result("multiple_simultaneous_violations")
        assert result.status is GridValidationStatus.UNSAFE
        v_types = {v.violation_type for v in result.violations}
        assert GridViolationType.OVER_VOLTAGE in v_types
        assert GridViolationType.LINE_OVERLOAD in v_types
        assert GridViolationType.TRANSFORMER_OVERLOAD in v_types
        assert len(result.violations) == 3

    def test_08_unrated_edge_downgrades_to_unknown(self) -> None:
        request = build_canonical_validation_request("unrated_edge_unknown_validation")
        assert len(request.network.unrated_elements) == 1

        # Even if engine reports SAFE, unrated element forces UNKNOWN
        downgraded = resolve_status(
            GridValidationStatus.SAFE, unrated_elements=request.network.unrated_elements
        )
        assert downgraded is GridValidationStatus.UNKNOWN
        decision = decide(status=downgraded, caused_violations=())
        assert decision is GridValidationDecision.REJECT

    def test_09_solver_failure_simulation(self) -> None:
        request = build_canonical_validation_request("solver_failure_unknown")
        failing_engine = FailingGridEngine()

        with pytest.raises(RuntimeError, match="did not converge"):
            failing_engine.validate(request)

    def test_10_safe_proposed_trade(self) -> None:
        request = build_canonical_validation_request("safe_proposed_trade")
        result = get_expected_validation_result("safe_proposed_trade")
        assert len(request.proposed_injections) == 2
        assert result.status is GridValidationStatus.SAFE
        assert len(result.caused_violations) == 0
        assert get_expected_decision("safe_proposed_trade") is GridValidationDecision.ACCEPT

    def test_11_unsafe_proposed_trade(self) -> None:
        result = get_expected_validation_result("unsafe_proposed_trade")
        assert result.status is GridValidationStatus.UNSAFE
        assert len(result.baseline_violations) == 0
        assert len(result.caused_violations) == 1
        assert result.caused_violations[0].violation_type is GridViolationType.LINE_OVERLOAD
        assert get_expected_decision("unsafe_proposed_trade") is GridValidationDecision.REJECT


class TestEngineExecutionAndDeterminism:
    """Execute StubGridEngine against scenarios to verify determinism."""

    @pytest.fixture
    def stub_engine(self) -> GridEngine:
        return StubGridEngine(name="stub-grid", engine_version="1.0.0")

    def test_engine_determinism(self, stub_engine: GridEngine) -> None:
        request = build_canonical_validation_request("healthy_radial_feeder")
        res1 = stub_engine.validate(request)
        res2 = stub_engine.validate(request)

        assert res1.status == res2.status
        assert res1.metrics == res2.metrics
        assert res1.violations == res2.violations
