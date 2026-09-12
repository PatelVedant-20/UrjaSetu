"""Power Grid Model adapter — the only production file that imports power_grid_model.

    GridValidationRequest
            │
            ▼
    _build_pgm_dataset(network, injections)
            │  UUID → stable integer ID mapping (separate namespaces for
            │  nodes vs edges, because UrjaSetu topology reuses node UUID
            │  as the edge identifier)
            │  Creates: node[], source[], line[], transformer[], sym_load[], sym_gen[]
            ▼
    PowerGridModel.calculate_power_flow()
            │  Newton–Raphson, symmetric three-phase
            ▼
    _extract_metrics(output, network, node_uuid_map, edge_uuid_map, ...)
            │  min/max u_pu from node results
            │  per-element loading_pct from line/transformer results
            ▼
    GridValidationResult
            (engine, engine_version, status, metrics, violations, baseline_violations)

Design decisions, stated once:

Physical parameters
    UrjaSetu's topology stores only `rated_capacity_kw` and `nominal_voltage_kv`.
    We do not store R/X/C per conductor; those belong in a future asset-level
    survey.  For this MVP we use default values typical of Indian LV distribution:

      Line: r₁ = 0.30 Ω/km, x₁ = 0.10 Ω/km, span = 50 m, i_n derived from
      rating_kw.

      Transformer: uk = 6%, pk = sn × 0.6%, i₀ = 1%, p₀ = sn × 0.2%,
      Wye-grounded/Wye-grounded, clock-12, 2-tap ±2×1%.

    These are explicit modelling assumptions, not hidden constants.

UUID → integer ID mapping
    PGM requires globally-unique positive integers across the entire input
    dataset.  UrjaSetu's topology reuses a node's UUID as the UUID of the
    edge connecting that node to its parent (transformer_id == transformer
    node's node_id, line_id == connection-point node's node_id).  To avoid
    conflicts, nodes and edges occupy separate integer namespaces allocated
    in a single pass.

Loading computation
    PGM's `line.loading` and `transformer.loading` are i/i_n fractions.
    `loading_pct = loading_fraction × 100` maps directly to the contract.
    Unrated elements use `i_n = 1 A` / `sn = 1 VA` as a placeholder so PGM
    accepts the model; their loading output is discarded and the
    `resolve_status` policy in `grid_limits` downgrades SAFE → UNKNOWN for
    any network containing unrated elements.

Solver failure
    Any exception from `PowerGridModel.calculate_power_flow` propagates
    upward.  `validate_scenario` in the service layer catches it and records
    an UNKNOWN run.  The adapter does NOT swallow failures and never returns
    SAFE for a network it did not actually solve.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
import power_grid_model as pgm

from app.domain.enums import GridValidationStatus, GridViolationType
from app.domain.interfaces.grid import (
    GridLimits,
    GridMetrics,
    GridValidationRequest,
    GridValidationResult,
    GridViolation,
    NetworkModel,
    NetworkNode,
    NodeInjection,
)
from app.domain.policies.grid_limits import evaluate_metrics

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

_LINE_LENGTH_KM = 0.050          # 50 m per span — explicit modelling assumption
_LINE_R1_OHM_PER_KM = 0.30
_LINE_X1_OHM_PER_KM = 0.10

_TX_SHORT_CIRCUIT_FRACTION = 0.06    # uk
_TX_COPPER_LOSS_FRACTION = 0.006     # pk / sn
_TX_NO_LOAD_CURRENT_FRAC = 0.010     # i₀
_TX_NO_LOAD_LOSS_FRAC = 0.002        # p₀ / sn

# Fallback VA / A rating for unrated elements so PGM accepts the model.
# Loading output for these elements is discarded.
_UNRATED_FALLBACK_VA = 1.0
_UNRATED_FALLBACK_AMP = 1.0

_SOURCE_U_REF = 1.0
_SOURCE_SK = 1e10       # VA — stiff infinite bus
_SOURCE_RX_RATIO = 0.1
_SOURCE_Z01_RATIO = 1.0

SQRT3 = math.sqrt(3)
ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# PGM dataset builder
# ---------------------------------------------------------------------------


def _build_pgm_dataset(
    network: NetworkModel,
    injections: Sequence[NodeInjection],
    *,
    id_offset: int = 0,
) -> tuple[dict[str, Any], dict[UUID, int], dict[UUID, int], int]:
    """Translate the domain network + injections into PGM input arrays.

    Returns:
        (input_data, node_uuid_to_pgm_id, edge_uuid_to_pgm_id, next_id)

    All PGM element IDs are globally unique within the model.  Nodes and
    edges (lines/transformers) occupy separate ranges because UrjaSetu's
    topology deliberately reuses a node's UUID as its incoming-edge UUID.
    """
    current_id = id_offset + 1

    # 1. Assign PGM IDs to nodes.
    node_uuid_to_id: dict[UUID, int] = {}
    for node in network.nodes:
        node_uuid_to_id[node.node_id] = current_id
        current_id += 1

    # 2. Assign PGM IDs to edges (separate integer namespace).
    edge_uuid_to_id: dict[UUID, int] = {}
    for line in network.lines:
        edge_uuid_to_id[line.line_id] = current_id
        current_id += 1
    for tx in network.transformers:
        edge_uuid_to_id[tx.transformer_id] = current_id
        current_id += 1

    known_node_ids = {n.node_id for n in network.nodes}
    node_by_id: dict[UUID, NetworkNode] = {n.node_id: n for n in network.nodes}

    # 3. Root nodes → slack bus.
    root_nodes = [
        n for n in network.nodes
        if n.parent_node_id is None or n.parent_node_id not in known_node_ids
    ]
    if not root_nodes:
        root_nodes = [network.nodes[0]]

    # --- node array ---
    node_arr = pgm.initialize_array("input", "node", len(network.nodes))
    for i, node in enumerate(network.nodes):
        node_arr["id"][i] = node_uuid_to_id[node.node_id]
        node_arr["u_rated"][i] = float(node.nominal_voltage_kv) * 1000.0  # V

    # --- source array ---
    source_arr = pgm.initialize_array("input", "source", len(root_nodes))
    for i, root in enumerate(root_nodes):
        source_arr["id"][i] = current_id
        current_id += 1
        source_arr["node"][i] = node_uuid_to_id[root.node_id]
        source_arr["status"][i] = 1
        source_arr["u_ref"][i] = _SOURCE_U_REF
        source_arr["sk"][i] = _SOURCE_SK
        source_arr["rx_ratio"][i] = _SOURCE_RX_RATIO
        source_arr["z01_ratio"][i] = _SOURCE_Z01_RATIO

    # --- line array ---
    lines_arr = pgm.initialize_array("input", "line", len(network.lines))
    for i, line in enumerate(network.lines):
        node_to = node_by_id.get(line.to_node_id)
        v_lv = float(node_to.nominal_voltage_kv) * 1000.0 if node_to else 400.0
        i_n = (
            float(line.rating_kw) * 1000.0 / (SQRT3 * v_lv)
            if line.rating_kw is not None
            else _UNRATED_FALLBACK_AMP
        )
        lines_arr["id"][i] = edge_uuid_to_id[line.line_id]
        lines_arr["from_node"][i] = node_uuid_to_id[line.from_node_id]
        lines_arr["to_node"][i] = node_uuid_to_id[line.to_node_id]
        lines_arr["from_status"][i] = 1
        lines_arr["to_status"][i] = 1
        lines_arr["r1"][i] = _LINE_R1_OHM_PER_KM * _LINE_LENGTH_KM
        lines_arr["x1"][i] = _LINE_X1_OHM_PER_KM * _LINE_LENGTH_KM
        lines_arr["c1"][i] = 0.0
        lines_arr["tan1"][i] = 0.0
        lines_arr["i_n"][i] = i_n

    # --- transformer array ---
    tx_arr = pgm.initialize_array("input", "transformer", len(network.transformers))
    for i, tx in enumerate(network.transformers):
        node_from = node_by_id.get(tx.from_node_id)
        node_to = node_by_id.get(tx.to_node_id)
        u1 = float(node_from.nominal_voltage_kv) * 1000.0 if node_from else 11000.0
        u2 = float(node_to.nominal_voltage_kv) * 1000.0 if node_to else 400.0
        sn = float(tx.rating_kw) * 1000.0 if tx.rating_kw is not None else _UNRATED_FALLBACK_VA

        tx_arr["id"][i] = edge_uuid_to_id[tx.transformer_id]
        tx_arr["from_node"][i] = node_uuid_to_id[tx.from_node_id]
        tx_arr["to_node"][i] = node_uuid_to_id[tx.to_node_id]
        tx_arr["from_status"][i] = 1
        tx_arr["to_status"][i] = 1
        tx_arr["u1"][i] = u1
        tx_arr["u2"][i] = u2
        tx_arr["sn"][i] = sn
        tx_arr["uk"][i] = _TX_SHORT_CIRCUIT_FRACTION
        tx_arr["pk"][i] = sn * _TX_COPPER_LOSS_FRACTION
        tx_arr["i0"][i] = _TX_NO_LOAD_CURRENT_FRAC
        tx_arr["p0"][i] = sn * _TX_NO_LOAD_LOSS_FRAC
        tx_arr["winding_from"][i] = 2    # Wye grounded
        tx_arr["winding_to"][i] = 2      # Wye grounded
        tx_arr["clock"][i] = 12
        tx_arr["tap_side"][i] = 0        # from_side
        tx_arr["tap_pos"][i] = 0
        tx_arr["tap_min"][i] = -2
        tx_arr["tap_max"][i] = 2
        tx_arr["tap_nom"][i] = 0
        tx_arr["tap_size"][i] = 0.01

    # --- injection arrays ---
    gen_injections = [
        inj for inj in injections
        if inj.active_power_kw > ZERO and inj.node_id in known_node_ids
    ]
    load_injections = [
        inj for inj in injections
        if inj.active_power_kw <= ZERO and inj.node_id in known_node_ids
    ]

    gen_arr = pgm.initialize_array("input", "sym_gen", len(gen_injections))
    for i, inj in enumerate(gen_injections):
        gen_arr["id"][i] = current_id
        current_id += 1
        gen_arr["node"][i] = node_uuid_to_id[inj.node_id]
        gen_arr["status"][i] = 1
        gen_arr["type"][i] = 0           # const_power
        gen_arr["p_specified"][i] = float(inj.active_power_kw) * 1000.0   # W
        gen_arr["q_specified"][i] = 0.0

    load_arr = pgm.initialize_array("input", "sym_load", len(load_injections))
    for i, inj in enumerate(load_injections):
        load_arr["id"][i] = current_id
        current_id += 1
        load_arr["node"][i] = node_uuid_to_id[inj.node_id]
        load_arr["status"][i] = 1
        load_arr["type"][i] = 0          # const_power
        load_arr["p_specified"][i] = abs(float(inj.active_power_kw)) * 1000.0  # W
        load_arr["q_specified"][i] = 0.0

    input_data: dict[str, Any] = {
        "node": node_arr,
        "source": source_arr,
    }
    if len(network.lines) > 0:
        input_data["line"] = lines_arr
    if len(network.transformers) > 0:
        input_data["transformer"] = tx_arr
    if len(gen_injections) > 0:
        input_data["sym_gen"] = gen_arr
    if len(load_injections) > 0:
        input_data["sym_load"] = load_arr

    return input_data, node_uuid_to_id, edge_uuid_to_id, current_id


# ---------------------------------------------------------------------------
# Output extraction
# ---------------------------------------------------------------------------


def _extract_metrics(
    output: dict[str, Any],
    network: NetworkModel,
    edge_uuid_to_id: dict[UUID, int],
    rated_lines: set[UUID],
    rated_transformers: set[UUID],
) -> tuple[GridMetrics, list[GridViolation]]:
    """Convert PGM output arrays into GridMetrics and per-element violations."""
    id_to_line_uuid: dict[int, UUID] = {
        edge_uuid_to_id[line.line_id]: line.line_id
        for line in network.lines
        if line.line_id in edge_uuid_to_id
    }
    id_to_tx_uuid: dict[int, UUID] = {
        edge_uuid_to_id[tx.transformer_id]: tx.transformer_id
        for tx in network.transformers
        if tx.transformer_id in edge_uuid_to_id
    }

    # Voltage metrics.
    min_v = max_v = None
    if "node" in output and len(output["node"]) > 0:
        u_pu_arr: np.ndarray = output["node"]["u_pu"]
        finite_mask = np.isfinite(u_pu_arr)
        if finite_mask.any():
            min_v = Decimal(str(round(float(u_pu_arr[finite_mask].min()), 6)))
            max_v = Decimal(str(round(float(u_pu_arr[finite_mask].max()), 6)))

    # Line loading (rated lines only).
    line_loadings: list[tuple[UUID, Decimal]] = []
    if "line" in output and len(output["line"]) > 0:
        for row in output["line"]:
            pgm_id = int(row["id"])
            line_uuid = id_to_line_uuid.get(pgm_id)
            if line_uuid is None or line_uuid not in rated_lines:
                continue
            loading_frac = float(row["loading"])
            if math.isfinite(loading_frac):
                line_loadings.append(
                    (line_uuid, Decimal(str(round(loading_frac * 100.0, 4))))
                )

    max_line_loading = max((v for _, v in line_loadings), default=None)

    # Transformer loading (rated transformers only).
    tx_loadings: list[tuple[UUID, Decimal]] = []
    if "transformer" in output and len(output["transformer"]) > 0:
        for row in output["transformer"]:
            pgm_id = int(row["id"])
            tx_uuid = id_to_tx_uuid.get(pgm_id)
            if tx_uuid is None or tx_uuid not in rated_transformers:
                continue
            loading_frac = float(row["loading"])
            if math.isfinite(loading_frac):
                tx_loadings.append(
                    (tx_uuid, Decimal(str(round(loading_frac * 100.0, 4))))
                )

    max_tx_loading = max((v for _, v in tx_loadings), default=None)

    metrics = GridMetrics(
        min_voltage_pu=min_v,
        max_voltage_pu=max_v,
        max_line_loading_pct=max_line_loading,
        max_transformer_loading_pct=max_tx_loading,
    )

    # Per-element violations (elements that breach 100 %).
    per_element_violations: list[GridViolation] = []
    for line_uuid, loading_pct in line_loadings:
        if loading_pct > Decimal("100"):
            per_element_violations.append(
                GridViolation(
                    violation_type=GridViolationType.LINE_OVERLOAD,
                    element_id=line_uuid,
                    observed=loading_pct,
                    limit=Decimal("100"),
                    detail=f"line loading {loading_pct}% exceeds rated capacity",
                )
            )
    for tx_uuid, loading_pct in tx_loadings:
        if loading_pct > Decimal("100"):
            per_element_violations.append(
                GridViolation(
                    violation_type=GridViolationType.TRANSFORMER_OVERLOAD,
                    element_id=tx_uuid,
                    observed=loading_pct,
                    limit=Decimal("100"),
                    detail=f"transformer loading {loading_pct}% exceeds rated capacity",
                )
            )

    return metrics, per_element_violations


def _run_power_flow(input_data: dict[str, Any]) -> dict[str, Any]:
    """Build and solve the PGM model. Propagates any solver exception upward."""
    model = pgm.PowerGridModel(input_data=input_data)
    return model.calculate_power_flow(
        calculation_method=pgm.CalculationMethod.newton_raphson
    )


def _determine_status(
    metrics: GridMetrics,
    limits: GridLimits,
    per_element_violations: list[GridViolation],
) -> GridValidationStatus:
    """Derive overall network status from metrics + per-element violations."""
    if per_element_violations:
        return GridValidationStatus.UNSAFE
    agg = evaluate_metrics(metrics, limits)
    if agg:
        return GridValidationStatus.UNSAFE
    return GridValidationStatus.SAFE


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class PowerGridModelAdapter:
    """GridEngine implemented with Power Grid Model 1.13.

    Satisfies the `GridEngine` Protocol structurally — no inheritance required.
    Power Grid Model is the only non-UrjaSetu import in this module, and this
    module is the only production file that imports it
    (docs/06_OPEN_SOURCE_INTEGRATION.md section 1).

    The adapter solves the network twice: once for the baseline (existing state)
    and once for baseline-plus-proposal combined.  Violations unique to the
    combined run are what the market attributes to the proposed trade.

    A baseline solve failure is non-fatal: the adapter conservatively assumes no
    pre-existing violations and proceeds to the combined solve.  A combined
    solve failure propagates as-is; the service layer records UNKNOWN.
    """

    NAME = "power_grid_model"
    VERSION: str = pgm.__version__

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def engine_version(self) -> str:
        return self.VERSION

    def validate(self, request: GridValidationRequest) -> GridValidationResult:
        """Run power flow and return normalised metrics and violations.

        Raises on solver failure — the contract explicitly requires this
        rather than returning SAFE with empty metrics.
        """
        network = request.network
        limits = request.limits

        rated_lines: set[UUID] = {
            ln.line_id for ln in network.lines if ln.rating_kw is not None
        }
        rated_transformers: set[UUID] = {
            tx.transformer_id for tx in network.transformers if tx.rating_kw is not None
        }

        # --- Baseline solve ---
        baseline_violations: list[GridViolation] = []
        try:
            b_data, _, b_edge_map, _ = _build_pgm_dataset(
                network, request.baseline_injections, id_offset=0
            )
            b_output = _run_power_flow(b_data)
            b_metrics, b_per_element = _extract_metrics(
                b_output, network, b_edge_map, rated_lines, rated_transformers
            )
            b_agg = list(evaluate_metrics(b_metrics, limits))
            baseline_violations = b_per_element + [
                v for v in b_agg
                if not any(v.violation_type == pv.violation_type for pv in b_per_element)
            ]
        except Exception:
            # Baseline failure → conservatively assume no pre-existing violations.
            baseline_violations = []

        # --- Combined solve (may raise → service records UNKNOWN) ---
        c_data, _, c_edge_map, _ = _build_pgm_dataset(
            network, request.combined_injections, id_offset=0
        )
        c_output = _run_power_flow(c_data)

        metrics, per_element_violations = _extract_metrics(
            c_output, network, c_edge_map, rated_lines, rated_transformers
        )

        status = _determine_status(metrics, limits, per_element_violations)

        agg_violations = list(evaluate_metrics(metrics, limits))
        # Per-element violations take priority; suppress duplicate aggregate types.
        all_violations = per_element_violations + [
            v for v in agg_violations
            if not any(v.violation_type == pv.violation_type for pv in per_element_violations)
        ]

        return GridValidationResult(
            engine=self.NAME,
            engine_version=self.VERSION,
            status=status,
            metrics=metrics,
            violations=tuple(all_violations),
            baseline_violations=tuple(baseline_violations),
        )
