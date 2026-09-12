"""Unit tests for PowerGridModelAdapter.

Pure: no database, no HTTP, no clock.  Exercises all required scenarios:
  1. healthy network → safe
  2. safe trade with injections → safe, correct metrics
  3. voltage violation
  4. line overload
  5. transformer overload
  6. multiple simultaneous violations
  7. UNKNOWN status on solver failure (exception propagated)
  8. UNKNOWN status when required rating is missing (via resolve_status)
  9. correct loading arithmetic
 10. deterministic output (same request → same result)
 11. domain contract purity (adapter imports in adapter module only)
 12. protocol conformance (isinstance check)
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

# Import the adapter here — only test file that may do so.
from app.adapters.grid.power_grid_model_adapter import PowerGridModelAdapter
from app.domain.enums import (
    GridNodeType,
    GridValidationStatus,
    GridViolationType,
)
from app.domain.interfaces.grid import (
    GridEngine,
    GridLimits,
    GridValidationRequest,
    NetworkLine,
    NetworkModel,
    NetworkNode,
    NetworkTransformer,
    NodeInjection,
)
from app.domain.policies.grid_limits import DEFAULT_LIMITS, resolve_status

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

T0 = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)

# Ratings that match Indian LV distribution norms used by the adapter.
TRANSFORMER_RATING_KW = Decimal("250")
LINE_RATING_KW = Decimal("60")


def _node(**kw: object) -> NetworkNode:
    defaults: dict[str, object] = {
        "node_id": uuid4(),
        "node_type": GridNodeType.CONNECTION_POINT,
        "nominal_voltage_kv": Decimal("0.4"),
    }
    return NetworkNode(**{**defaults, **kw})  # type: ignore[arg-type]


def _make_radial() -> tuple[NetworkModel, dict[str, object]]:
    """Substation (11 kV) → transformer node (0.4 kV) → connection point (0.4 kV)."""
    sub_id = uuid4()
    tx_id = uuid4()
    cp_id = uuid4()

    sub = NetworkNode(
        node_id=sub_id,
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11"),
    )
    tx_node = NetworkNode(
        node_id=tx_id,
        node_type=GridNodeType.TRANSFORMER,
        nominal_voltage_kv=Decimal("0.4"),
        parent_node_id=sub_id,
    )
    cp = NetworkNode(
        node_id=cp_id,
        node_type=GridNodeType.CONNECTION_POINT,
        nominal_voltage_kv=Decimal("0.4"),
        parent_node_id=tx_id,
    )
    transformer = NetworkTransformer(
        transformer_id=tx_id,
        from_node_id=sub_id,
        to_node_id=tx_id,
        rating_kw=TRANSFORMER_RATING_KW,
    )
    line = NetworkLine(
        line_id=cp_id,
        from_node_id=tx_id,
        to_node_id=cp_id,
        rating_kw=LINE_RATING_KW,
    )
    network = NetworkModel(
        version="test-radial",
        nodes=(sub, tx_node, cp),
        lines=(line,),
        transformers=(transformer,),
    )
    return network, {"sub_id": sub_id, "tx_id": tx_id, "cp_id": cp_id}


def _request(
    network: NetworkModel,
    *,
    energy_kwh: Decimal,
    seller_node_id: object,
    buyer_node_id: object,
    baseline_injections: tuple[NodeInjection, ...] = (),
    limits: GridLimits = DEFAULT_LIMITS,
) -> GridValidationRequest:
    from uuid import UUID

    s_id = seller_node_id if isinstance(seller_node_id, UUID) else uuid4()
    b_id = buyer_node_id if isinstance(buyer_node_id, UUID) else uuid4()
    seller = NodeInjection.from_energy(node_id=s_id, energy_kwh=energy_kwh, interval=HOUR)
    buyer = NodeInjection(node_id=b_id, active_power_kw=-seller.active_power_kw)
    return GridValidationRequest(
        network=network,
        limits=limits,
        interval_start=T0,
        interval_end=T0 + HOUR,
        baseline_injections=baseline_injections,
        proposed_injections=(seller, buyer),
    )


# ---------------------------------------------------------------------------
# Test 1: healthy network → SAFE
# ---------------------------------------------------------------------------


def test_healthy_trade_is_safe() -> None:
    """A small trade on an unloaded radial feeder is SAFE."""
    network, ids = _make_radial()
    engine = PowerGridModelAdapter()

    result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("10"),
            seller_node_id=ids["sub_id"],
            buyer_node_id=ids["cp_id"],
        )
    )

    assert result.status is GridValidationStatus.SAFE
    assert result.safe is True
    assert not result.violations


# ---------------------------------------------------------------------------
# Test 2: metrics are produced correctly for a safe trade
# ---------------------------------------------------------------------------


def test_safe_trade_produces_all_metrics() -> None:
    """All four metric fields are populated for a solved network."""
    network, ids = _make_radial()
    engine = PowerGridModelAdapter()

    result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("10"),
            seller_node_id=ids["sub_id"],
            buyer_node_id=ids["cp_id"],
        )
    )

    m = result.metrics
    assert m.min_voltage_pu is not None
    assert m.max_voltage_pu is not None
    assert m.max_line_loading_pct is not None
    assert m.max_transformer_loading_pct is not None
    # Voltage must be within the ±6 % Indian LV band.
    assert m.min_voltage_pu >= Decimal("0.94")
    assert m.max_voltage_pu <= Decimal("1.06")


# ---------------------------------------------------------------------------
# Test 3: voltage violation → UNSAFE
# ---------------------------------------------------------------------------


def test_voltage_violation_detected() -> None:
    """A network whose voltage falls below the floor is reported UNSAFE.

    We build a custom GridLimits with a very tight floor that the healthy
    network (min ≈ 0.994 pu for 10 kW) will breach, without needing to
    force an extreme injection.
    """
    network, ids = _make_radial()
    tight_limits = GridLimits(
        min_voltage_pu=Decimal("0.999"),  # tighter than the 10 kW drop
        max_voltage_pu=Decimal("1.06"),
        max_line_loading_pct=Decimal("100"),
        max_transformer_loading_pct=Decimal("100"),
    )
    engine = PowerGridModelAdapter()

    result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("10"),
            seller_node_id=ids["sub_id"],
            buyer_node_id=ids["cp_id"],
            limits=tight_limits,
        )
    )

    assert result.status is GridValidationStatus.UNSAFE
    violation_types = {v.violation_type for v in result.violations}
    assert GridViolationType.UNDER_VOLTAGE in violation_types


# ---------------------------------------------------------------------------
# Test 4: line overload → UNSAFE
# ---------------------------------------------------------------------------


def test_line_overload_detected() -> None:
    """A trade whose power exceeds the line rating is UNSAFE with LINE_OVERLOAD."""
    network, ids = _make_radial()
    engine = PowerGridModelAdapter()

    # 70 kW > 60 kW line rating → overload.
    result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("70"),
            seller_node_id=ids["sub_id"],
            buyer_node_id=ids["cp_id"],
        )
    )

    assert result.status is GridValidationStatus.UNSAFE
    violation_types = {v.violation_type for v in result.violations}
    assert GridViolationType.LINE_OVERLOAD in violation_types
    # The violation carries the element UUID.
    line_violations = [
        v for v in result.violations if v.violation_type is GridViolationType.LINE_OVERLOAD
    ]
    assert line_violations[0].element_id is not None


# ---------------------------------------------------------------------------
# Test 5: transformer overload → UNSAFE
# ---------------------------------------------------------------------------


def test_transformer_overload_detected() -> None:
    """A trade whose power exceeds the transformer rating is UNSAFE."""
    network, ids = _make_radial()
    engine = PowerGridModelAdapter()

    # 280 kW > 250 kW transformer rating → overload.
    result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("280"),
            seller_node_id=ids["sub_id"],
            buyer_node_id=ids["cp_id"],
        )
    )

    assert result.status is GridValidationStatus.UNSAFE
    violation_types = {v.violation_type for v in result.violations}
    assert GridViolationType.TRANSFORMER_OVERLOAD in violation_types


# ---------------------------------------------------------------------------
# Test 6: multiple simultaneous violations
# ---------------------------------------------------------------------------


def test_multiple_violations_reported() -> None:
    """An extreme trade can breach both line and transformer simultaneously."""
    network, ids = _make_radial()
    engine = PowerGridModelAdapter()

    # 400 kW overloads both the 60 kW line and the 250 kW transformer.
    result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("400"),
            seller_node_id=ids["sub_id"],
            buyer_node_id=ids["cp_id"],
        )
    )

    assert result.status is GridValidationStatus.UNSAFE
    violation_types = {v.violation_type for v in result.violations}
    assert GridViolationType.LINE_OVERLOAD in violation_types
    assert GridViolationType.TRANSFORMER_OVERLOAD in violation_types


# ---------------------------------------------------------------------------
# Test 7: solver failure → exception propagates (service records UNKNOWN)
# ---------------------------------------------------------------------------


def test_solver_failure_propagates_exception() -> None:
    """A network PGM cannot validate raises; the adapter does not swallow it.

    We build a network with a line whose from-node and to-node have conflicting
    voltage ratings (11 kV vs 0.4 kV) — PGM raises ConflictVoltage for a line
    (not a transformer) connecting different voltage levels.  This exercises
    the path where the combined solve raises and the adapter propagates it.
    """
    sub_id = uuid4()
    cp_id = uuid4()
    sub = NetworkNode(
        node_id=sub_id,
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11"),
    )
    cp = NetworkNode(
        node_id=cp_id,
        node_type=GridNodeType.CONNECTION_POINT,
        nominal_voltage_kv=Decimal("0.4"),
        parent_node_id=sub_id,
    )
    # A *line* (not transformer) connecting 11 kV to 0.4 kV is invalid in PGM.
    bad_line = NetworkLine(
        line_id=cp_id,
        from_node_id=sub_id,
        to_node_id=cp_id,
        rating_kw=Decimal("60"),
    )
    network = NetworkModel(
        version="conflicting-voltage",
        nodes=(sub, cp),
        lines=(bad_line,),
        transformers=(),
    )
    engine = PowerGridModelAdapter()

    seller = NodeInjection.from_energy(node_id=sub_id, energy_kwh=Decimal("5"), interval=HOUR)
    buyer = NodeInjection(node_id=cp_id, active_power_kw=-seller.active_power_kw)
    request = GridValidationRequest(
        network=network,
        limits=DEFAULT_LIMITS,
        interval_start=T0,
        interval_end=T0 + HOUR,
        proposed_injections=(seller, buyer),
    )

    # The adapter MUST propagate the failure, not return SAFE. Narrowed from a
    # bare `Exception` so the test cannot pass on an unrelated error such as a
    # TypeError in the request it was handed.
    with pytest.raises((RuntimeError, ValueError)):
        engine.validate(request)


# ---------------------------------------------------------------------------
# Test 8: UNKNOWN when a required rating is missing
# ---------------------------------------------------------------------------


def test_unrated_element_causes_unknown_via_resolve_status() -> None:
    """A network with an unrated line produces SAFE from the solver; resolve_status
    downgrades it to UNKNOWN because thermal limits cannot be assessed.

    The network uses same-voltage (0.4 kV) nodes so the line is valid for PGM.
    """
    sub_id = uuid4()
    tx_id = uuid4()
    cp_id = uuid4()
    sub = NetworkNode(
        node_id=sub_id,
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11"),
    )
    tx_node = NetworkNode(
        node_id=tx_id,
        node_type=GridNodeType.TRANSFORMER,
        nominal_voltage_kv=Decimal("0.4"),
        parent_node_id=sub_id,
    )
    cp = NetworkNode(
        node_id=cp_id,
        node_type=GridNodeType.CONNECTION_POINT,
        nominal_voltage_kv=Decimal("0.4"),
        parent_node_id=tx_id,
    )
    # Rated transformer so PGM can solve; unrated line (rating_kw=None).
    transformer = NetworkTransformer(
        transformer_id=tx_id,
        from_node_id=sub_id,
        to_node_id=tx_id,
        rating_kw=TRANSFORMER_RATING_KW,
    )
    unrated_line = NetworkLine(
        line_id=cp_id,
        from_node_id=tx_id,
        to_node_id=cp_id,
        rating_kw=None,  # ← unrated
    )
    network = NetworkModel(
        version="unrated",
        nodes=(sub, tx_node, cp),
        lines=(unrated_line,),
        transformers=(transformer,),
    )

    engine = PowerGridModelAdapter()
    raw_result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("5"),
            seller_node_id=sub_id,
            buyer_node_id=cp_id,
        )
    )

    # The adapter itself returns SAFE; the service layer calls resolve_status
    # to downgrade it to UNKNOWN because the line has no rating.
    unrated = network.unrated_elements
    effective = resolve_status(raw_result.status, unrated_elements=unrated)
    assert effective is GridValidationStatus.UNKNOWN
    assert len(unrated) == 1


# ---------------------------------------------------------------------------
# Test 9: loading arithmetic is correct
# ---------------------------------------------------------------------------


def test_loading_arithmetic_is_correct() -> None:
    """Loading percentage = (i_actual / i_rated) × 100, not a kW ratio."""
    network, ids = _make_radial()
    engine = PowerGridModelAdapter()

    result = engine.validate(
        _request(
            network,
            energy_kwh=Decimal("10"),
            seller_node_id=ids["sub_id"],
            buyer_node_id=ids["cp_id"],
        )
    )

    m = result.metrics
    assert m.max_line_loading_pct is not None
    # 10 kW on a 60 kW rated line: i_actual ≈ 10/60 × i_n ≈ 16.7 %
    # With voltage drop the percentage will be slightly different but should be << 50.
    assert m.max_line_loading_pct < Decimal(
        "50"
    ), f"expected <50% loading for a 10 kW trade on a 60 kW line, got {m.max_line_loading_pct}"
    # Should definitely not be zero (actual flow is happening).
    assert m.max_line_loading_pct > Decimal("0")


# ---------------------------------------------------------------------------
# Test 10: deterministic output
# ---------------------------------------------------------------------------


def test_deterministic_output() -> None:
    """The same request always produces the same result."""
    network, ids = _make_radial()
    engine = PowerGridModelAdapter()

    req = _request(
        network,
        energy_kwh=Decimal("25"),
        seller_node_id=ids["sub_id"],
        buyer_node_id=ids["cp_id"],
    )
    result1 = engine.validate(req)
    result2 = engine.validate(req)

    assert result1.status is result2.status
    assert result1.metrics == result2.metrics
    assert result1.violations == result2.violations


# ---------------------------------------------------------------------------
# Test 11: domain contract purity
# ---------------------------------------------------------------------------


def test_adapter_is_the_only_production_importer_of_power_grid_model() -> None:
    """No production file outside `adapters/grid/` imports power_grid_model."""
    offenders: list[str] = []
    for path in Path("backend/app").rglob("*.py"):
        if "adapters/grid" in path.as_posix():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names: set[str] = set()
            if isinstance(node, ast.Import):
                names = {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = {node.module}
            if any(n == "power_grid_model" or n.startswith("power_grid_model.") for n in names):
                offenders.append(str(path))
                break

    assert not offenders, f"power_grid_model imported outside adapter: {offenders}"


# ---------------------------------------------------------------------------
# Test 12: protocol conformance
# ---------------------------------------------------------------------------


def test_adapter_satisfies_grid_engine_protocol() -> None:
    """PowerGridModelAdapter satisfies the GridEngine Protocol via isinstance."""
    engine = PowerGridModelAdapter()
    assert isinstance(engine, GridEngine)
    assert engine.name == "power_grid_model"
    assert engine.engine_version == "1.13.162"
