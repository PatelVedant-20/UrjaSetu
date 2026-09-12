"""Loader utility for Phase 5 Grid Scenarios and Fixtures.

Consumes canonical domain contracts and models:
    NetworkModel, NetworkNode, NetworkLine, NetworkTransformer, NodeInjection,
    GridLimits, GridMetrics, GridViolation, GridValidationRequest, GridValidationResult,
    GridNodeType, GridValidationDecision, GridValidationStatus, GridViolationType
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from app.domain.enums import (
    GridNodeType,
    GridValidationDecision,
    GridValidationStatus,
    GridViolationType,
)
from app.domain.interfaces.grid import (
    GridLimits,
    GridMetrics,
    GridValidationRequest,
    GridValidationResult,
    GridViolation,
    NetworkLine,
    NetworkModel,
    NetworkNode,
    NetworkTransformer,
    NodeInjection,
)


def get_grid_fixtures_dir() -> Path:
    """Resolve the absolute path to data/synthetic/grid."""
    base = Path(__file__).resolve()
    # backend/tests/fixtures/grid/loader.py -> repo root
    repo_root = base.parents[4]
    fixtures_dir = repo_root / "data" / "synthetic" / "grid"
    if not fixtures_dir.exists():
        raise FileNotFoundError(f"Grid fixtures directory not found: {fixtures_dir}")
    return fixtures_dir


def load_grid_manifest() -> dict[str, Any]:
    """Load the master grid manifest."""
    manifest_path = get_grid_fixtures_dir() / "grid_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Grid manifest not found: {manifest_path}")
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


def list_available_grid_scenarios() -> list[str]:
    """Return list of available scenario identifiers."""
    manifest = load_grid_manifest()
    return list(manifest.get("scenarios", {}).keys())


def _resolve_fixture_path(scenario_name: str) -> Path:
    fixtures_dir = get_grid_fixtures_dir()
    if scenario_name.endswith(".json"):
        path = fixtures_dir / scenario_name
        if path.exists():
            return path

    manifest = load_grid_manifest()
    scenarios = manifest.get("scenarios", {})
    if scenario_name in scenarios:
        filename = scenarios[scenario_name]["file"]
        return fixtures_dir / filename

    candidate = fixtures_dir / f"{scenario_name}.json"
    if candidate.exists():
        return candidate

    for entry in scenarios.values():
        if entry.get("file", "").endswith(f"{scenario_name}.json"):
            return fixtures_dir / entry["file"]

    raise FileNotFoundError(
        f"Grid scenario fixture '{scenario_name}' not found. Available: {list(scenarios.keys())}"
    )


def load_grid_fixture(scenario_name: str) -> dict[str, Any]:
    """Load raw JSON fixture data for a scenario."""
    fixture_path = _resolve_fixture_path(scenario_name)
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


def _parse_utc_datetime(iso_str: str) -> datetime:
    """Parse ISO datetime and ensure UTC timezone."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.astimezone(UTC)


def build_canonical_network_model(scenario_name: str) -> NetworkModel:
    """Project scenario nodes into canonical NetworkModel (nodes, lines, transformers)."""
    data = load_grid_fixture(scenario_name)
    top_data = data["topology"]
    version = top_data.get("version", "phase-5-ahmedabad-feeder-1")

    raw_nodes = top_data.get("nodes", [])

    network_nodes: list[NetworkNode] = []
    ratings: dict[UUID, Decimal | None] = {}

    for n in raw_nodes:
        nid = UUID(n["id"])
        parent_id = UUID(n["parent_node_id"]) if n.get("parent_node_id") else None
        node_type = GridNodeType(n["node_type"])
        voltage = Decimal(str(n["nominal_voltage_kv"]))

        network_nodes.append(
            NetworkNode(
                node_id=nid,
                node_type=node_type,
                nominal_voltage_kv=voltage,
                parent_node_id=parent_id,
                feeder_id=n.get("feeder_id"),
            )
        )

        cap = n.get("rated_capacity_kw")
        ratings[nid] = Decimal(str(cap)) if cap is not None else None

    known = {node.node_id for node in network_nodes}
    lines: list[NetworkLine] = []
    transformers: list[NetworkTransformer] = []

    for node in network_nodes:
        if node.parent_node_id is None or node.parent_node_id not in known:
            continue
        if node.node_type is GridNodeType.TRANSFORMER:
            transformers.append(
                NetworkTransformer(
                    transformer_id=node.node_id,
                    from_node_id=node.parent_node_id,
                    to_node_id=node.node_id,
                    rating_kw=ratings.get(node.node_id),
                )
            )
        else:
            lines.append(
                NetworkLine(
                    line_id=node.node_id,
                    from_node_id=node.parent_node_id,
                    to_node_id=node.node_id,
                    rating_kw=ratings.get(node.node_id),
                )
            )

    return NetworkModel(
        version=version,
        nodes=tuple(network_nodes),
        lines=tuple(lines),
        transformers=tuple(transformers),
    )


def build_canonical_validation_request(scenario_name: str) -> GridValidationRequest:
    """Build canonical GridValidationRequest from scenario fixture."""
    data = load_grid_fixture(scenario_name)
    network = build_canonical_network_model(scenario_name)

    lim_data = data.get("limits", {})
    limits = GridLimits(
        min_voltage_pu=Decimal(str(lim_data["min_voltage_pu"])),
        max_voltage_pu=Decimal(str(lim_data["max_voltage_pu"])),
        max_line_loading_pct=Decimal(str(lim_data["max_line_loading_pct"])),
        max_transformer_loading_pct=Decimal(str(lim_data["max_transformer_loading_pct"])),
    )

    t_start = _parse_utc_datetime(data["interval_start"])
    t_end = _parse_utc_datetime(data["interval_end"])

    baseline = tuple(
        NodeInjection(
            node_id=UUID(inj["node_id"]),
            active_power_kw=Decimal(str(inj["active_power_kw"])),
        )
        for inj in data.get("baseline_injections", [])
    )

    proposed = tuple(
        NodeInjection(
            node_id=UUID(inj["node_id"]),
            active_power_kw=Decimal(str(inj["active_power_kw"])),
        )
        for inj in data.get("proposed_injections", [])
    )

    return GridValidationRequest(
        network=network,
        limits=limits,
        interval_start=t_start,
        interval_end=t_end,
        baseline_injections=baseline,
        proposed_injections=proposed,
    )


def get_expected_validation_result(
    scenario_name: str,
    engine_name: str = "stub-grid",
    engine_version: str = "1.0.0",
) -> GridValidationResult:
    """Extract expected GridValidationResult from scenario fixture."""
    data = load_grid_fixture(scenario_name)
    exp = data.get("expected_validation", {})

    status = GridValidationStatus(exp["status"])

    m_data = exp.get("metrics", {})
    metrics = GridMetrics(
        min_voltage_pu=Decimal(str(m_data["min_voltage_pu"]))
        if m_data.get("min_voltage_pu") is not None
        else None,
        max_voltage_pu=Decimal(str(m_data["max_voltage_pu"]))
        if m_data.get("max_voltage_pu") is not None
        else None,
        max_line_loading_pct=Decimal(str(m_data["max_line_loading_pct"]))
        if m_data.get("max_line_loading_pct") is not None
        else None,
        max_transformer_loading_pct=Decimal(str(m_data["max_transformer_loading_pct"]))
        if m_data.get("max_transformer_loading_pct") is not None
        else None,
    )

    violations = tuple(
        GridViolation(
            violation_type=GridViolationType(v["violation_type"]),
            element_id=UUID(v["element_id"]) if v.get("element_id") else None,
            observed=Decimal(str(v["observed"])),
            limit=Decimal(str(v["limit"])),
            detail=v.get("detail"),
        )
        for v in exp.get("violations", [])
    )

    base_violations = tuple(
        GridViolation(
            violation_type=GridViolationType(v["violation_type"]),
            element_id=UUID(v["element_id"]) if v.get("element_id") else None,
            observed=Decimal(str(v["observed"])),
            limit=Decimal(str(v["limit"])),
            detail=v.get("detail"),
        )
        for v in exp.get("baseline_violations", [])
    )

    return GridValidationResult(
        engine=engine_name,
        engine_version=engine_version,
        status=status,
        metrics=metrics,
        violations=violations,
        baseline_violations=base_violations,
    )


def get_expected_decision(scenario_name: str) -> GridValidationDecision:
    """Extract expected GridValidationDecision (ACCEPT / REJECT)."""
    data = load_grid_fixture(scenario_name)
    dec_str = data["expected_validation"]["decision"]
    return GridValidationDecision(dec_str)
