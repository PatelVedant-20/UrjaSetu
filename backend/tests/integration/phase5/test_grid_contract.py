"""Phase 5: the grid contract and limits policy.

Pure: no database, no solver, no clock. Covers the contract shape, the
units boundary, and the limit/decision policy.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.domain.enums import (
    GridNodeType,
    GridValidationDecision,
    GridValidationStatus,
    GridViolationType,
)
from app.domain.interfaces.grid import (
    GridEngine,
    GridLimits,
    GridMetrics,
    GridValidationRequest,
    GridValidationResult,
    GridViolation,
    NetworkModel,
    NetworkNode,
    NodeInjection,
)
from app.domain.policies.grid_limits import DEFAULT_LIMITS, decide, evaluate_metrics, summarise

T0 = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _node(**kw: object) -> NetworkNode:
    defaults: dict[str, object] = {
        "node_id": uuid4(),
        "node_type": GridNodeType.CONNECTION_POINT,
        "nominal_voltage_kv": Decimal("0.4"),
    }
    return NetworkNode(**{**defaults, **kw})  # type: ignore[arg-type]


def _request(**kw: object) -> GridValidationRequest:
    defaults: dict[str, object] = {
        "network": NetworkModel(version="test", nodes=(_node(),)),
        "limits": DEFAULT_LIMITS,
        "interval_start": T0,
        "interval_end": T0 + HOUR,
    }
    return GridValidationRequest(**{**defaults, **kw})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. GridEngine contract
# ---------------------------------------------------------------------------


class ThirdPartySolver:
    """A solver written with no knowledge of UrjaSetu's internals."""

    name = "third-party"
    engine_version = "0.1"

    def validate(self, request: GridValidationRequest) -> GridValidationResult:
        return GridValidationResult(
            engine=self.name,
            engine_version=self.engine_version,
            status=GridValidationStatus.SAFE,
            metrics=GridMetrics(min_voltage_pu=Decimal("1.0")),
        )


def test_an_unrelated_class_satisfies_the_engine_type() -> None:
    engine: GridEngine = ThirdPartySolver()

    assert isinstance(engine, GridEngine)
    assert engine.name == "third-party"


def test_the_contract_imports_no_solver_persistence_or_transport() -> None:
    """Power Grid Model must live behind the adapter and nowhere else."""
    import app.domain.interfaces.grid as contract

    assert contract.__file__ is not None
    tree = ast.parse(Path(contract.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = (
        "power_grid_model",
        "sqlalchemy",
        "fastapi",
        "app.db",
        "app.repositories",
        "app.adapters",
        "app.api",
    )
    offending = [n for n in imported if any(n == f or n.startswith(f + ".") for f in forbidden)]
    assert not offending, f"the grid contract must not import {offending}"


def test_no_application_layer_imports_power_grid_model() -> None:
    """Only `app/adapters/grid/` may *import* the solver.

    Checked on imports rather than on source text, so a module is free to name
    the adapter in its documentation while depending on nothing.
    """
    offenders: list[str] = []
    for path in Path("backend/app").rglob("*.py"):
        if "adapters/grid" in str(path.as_posix()):
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

    assert not offenders, f"Power Grid Model imported outside its adapter: {offenders}"


# ---------------------------------------------------------------------------
# 2. Request / result types
# ---------------------------------------------------------------------------


def test_contract_objects_are_immutable() -> None:
    for obj, attr, value in (
        (_node(), "nominal_voltage_kv", Decimal("99")),
        (
            NodeInjection(node_id=uuid4(), active_power_kw=Decimal("1")),
            "active_power_kw",
            Decimal("9"),
        ),
        (GridMetrics(), "min_voltage_pu", Decimal("1")),
    ):
        try:
            setattr(obj, attr, value)
        except Exception as exc:
            assert exc.__class__.__name__ == "FrozenInstanceError"
        else:  # pragma: no cover - a mutable contract object is a defect
            raise AssertionError(f"{type(obj).__name__}.{attr} should be immutable")


def test_baseline_and_proposal_are_combined_per_node() -> None:
    """Every engine must superpose the same way, or results are incomparable."""
    node = uuid4()
    request = _request(
        baseline_injections=(NodeInjection(node_id=node, active_power_kw=Decimal("-3")),),
        proposed_injections=(NodeInjection(node_id=node, active_power_kw=Decimal("5")),),
    )

    combined = request.combined_injections

    assert len(combined) == 1
    assert combined[0].active_power_kw == Decimal("2")


def test_result_separates_caused_from_pre_existing_violations() -> None:
    """A trade must not be blamed for a problem the feeder already had."""
    element = uuid4()
    pre_existing = GridViolation(
        violation_type=GridViolationType.LINE_OVERLOAD,
        element_id=element,
        observed=Decimal("110"),
        limit=Decimal("100"),
    )
    worse = GridViolation(
        violation_type=GridViolationType.LINE_OVERLOAD,
        element_id=element,
        observed=Decimal("130"),
        limit=Decimal("100"),
    )
    fresh = GridViolation(
        violation_type=GridViolationType.UNDER_VOLTAGE,
        element_id=uuid4(),
        observed=Decimal("0.90"),
        limit=Decimal("0.94"),
    )
    result = GridValidationResult(
        engine="e",
        engine_version="1",
        status=GridValidationStatus.UNSAFE,
        metrics=GridMetrics(),
        violations=(worse, fresh),
        baseline_violations=(pre_existing,),
    )

    caused = result.caused_violations

    assert len(caused) == 1
    assert caused[0].violation_type is GridViolationType.UNDER_VOLTAGE


def test_violation_margin_is_positive_in_both_directions() -> None:
    """Severity is comparable across a breached floor and an exceeded ceiling."""
    under = GridViolation(
        violation_type=GridViolationType.UNDER_VOLTAGE,
        element_id=None,
        observed=Decimal("0.90"),
        limit=Decimal("0.94"),
    )
    over = GridViolation(
        violation_type=GridViolationType.OVER_VOLTAGE,
        element_id=None,
        observed=Decimal("1.10"),
        limit=Decimal("1.06"),
    )

    assert under.margin == Decimal("0.04")
    assert over.margin == Decimal("0.04")


# ---------------------------------------------------------------------------
# 3. Units boundary — kWh to kW
# ---------------------------------------------------------------------------


def test_energy_converts_to_average_power_over_the_interval() -> None:
    """10 kWh delivered evenly across an hour is 10 kW."""
    injection = NodeInjection.from_energy(node_id=uuid4(), energy_kwh=Decimal("10"), interval=HOUR)

    assert injection.active_power_kw == Decimal("10")


def test_a_shorter_interval_means_a_higher_power() -> None:
    """The same energy in a quarter of the time is four times the power.

    This is exactly why validation uses the committed delivery window rather
    than a longer, flattering one.
    """
    injection = NodeInjection.from_energy(
        node_id=uuid4(), energy_kwh=Decimal("10"), interval=timedelta(minutes=15)
    )

    assert injection.active_power_kw == Decimal("40")


def test_a_zero_length_interval_cannot_be_converted() -> None:
    """Dividing energy by no time is undefined, not infinite."""
    with pytest.raises(ValueError, match="positive duration"):
        NodeInjection.from_energy(node_id=uuid4(), energy_kwh=Decimal("10"), interval=timedelta(0))


def test_sign_convention_is_generation_positive() -> None:
    """A seller injects; the buyer's withdrawal is the negative of it."""
    seller = NodeInjection.from_energy(node_id=uuid4(), energy_kwh=Decimal("6"), interval=HOUR)
    buyer = NodeInjection(node_id=uuid4(), active_power_kw=-seller.active_power_kw)

    assert seller.active_power_kw > 0
    assert buyer.active_power_kw < 0
    assert seller.active_power_kw + buyer.active_power_kw == Decimal("0")


# ---------------------------------------------------------------------------
# 4. Limits and decision policy
# ---------------------------------------------------------------------------


def test_a_healthy_network_has_no_violations() -> None:
    metrics = GridMetrics(
        min_voltage_pu=Decimal("0.99"),
        max_voltage_pu=Decimal("1.01"),
        max_line_loading_pct=Decimal("40"),
        max_transformer_loading_pct=Decimal("55"),
    )

    assert evaluate_metrics(metrics, DEFAULT_LIMITS) == ()
    assert (
        decide(status=GridValidationStatus.SAFE, caused_violations=())
        is GridValidationDecision.ACCEPT
    )


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        (GridMetrics(min_voltage_pu=Decimal("0.90")), GridViolationType.UNDER_VOLTAGE),
        (GridMetrics(max_voltage_pu=Decimal("1.10")), GridViolationType.OVER_VOLTAGE),
        (GridMetrics(max_line_loading_pct=Decimal("120")), GridViolationType.LINE_OVERLOAD),
        (
            GridMetrics(max_transformer_loading_pct=Decimal("140")),
            GridViolationType.TRANSFORMER_OVERLOAD,
        ),
    ],
)
def test_each_constraint_class_is_detected(
    metrics: GridMetrics, expected: GridViolationType
) -> None:
    violations = evaluate_metrics(metrics, DEFAULT_LIMITS)

    assert [v.violation_type for v in violations] == [expected]


def test_limits_are_configurable_not_hard_coded() -> None:
    """A rural spur and a dense urban feeder are not held to the same numbers."""
    metrics = GridMetrics(min_voltage_pu=Decimal("0.92"))
    strict = GridLimits(
        min_voltage_pu=Decimal("0.95"),
        max_voltage_pu=Decimal("1.05"),
        max_line_loading_pct=Decimal("100"),
        max_transformer_loading_pct=Decimal("100"),
    )
    relaxed = GridLimits(
        min_voltage_pu=Decimal("0.90"),
        max_voltage_pu=Decimal("1.10"),
        max_line_loading_pct=Decimal("100"),
        max_transformer_loading_pct=Decimal("100"),
    )

    assert evaluate_metrics(metrics, strict)
    assert evaluate_metrics(metrics, relaxed) == ()


def test_limits_are_inclusive_at_the_boundary() -> None:
    """Exactly at the limit is within it, so the rule has no ambiguous value."""
    at_limit = GridMetrics(
        min_voltage_pu=DEFAULT_LIMITS.min_voltage_pu,
        max_voltage_pu=DEFAULT_LIMITS.max_voltage_pu,
        max_line_loading_pct=DEFAULT_LIMITS.max_line_loading_pct,
    )

    assert evaluate_metrics(at_limit, DEFAULT_LIMITS) == ()


def test_unmeasured_metrics_raise_no_violation() -> None:
    """None means not computed — never a silent pass or a silent failure."""
    assert evaluate_metrics(GridMetrics(), DEFAULT_LIMITS) == ()


def test_an_unsafe_network_is_rejected_even_with_no_caused_violations() -> None:
    """A network the engine calls unsafe is never accepted as 'pre-existing'."""
    assert (
        decide(status=GridValidationStatus.UNSAFE, caused_violations=())
        is GridValidationDecision.REJECT
    )


def test_a_trade_that_causes_a_violation_is_rejected() -> None:
    caused = evaluate_metrics(GridMetrics(max_line_loading_pct=Decimal("130")), DEFAULT_LIMITS)

    assert (
        decide(status=GridValidationStatus.SAFE, caused_violations=caused)
        is GridValidationDecision.REJECT
    )


def test_this_phase_emits_only_accept_or_reject() -> None:
    """Remediation decisions belong to the grid-aware feedback phase."""
    outcomes = {
        decide(status=GridValidationStatus.SAFE, caused_violations=()),
        decide(status=GridValidationStatus.UNSAFE, caused_violations=()),
    }

    assert outcomes == {GridValidationDecision.ACCEPT, GridValidationDecision.REJECT}
    assert GridValidationDecision.REDUCE.requires_remediation is True


def test_reason_summary_is_stable() -> None:
    """The same violations must always read the same way."""
    metrics = GridMetrics(min_voltage_pu=Decimal("0.90"), max_line_loading_pct=Decimal("120"))
    violations = evaluate_metrics(metrics, DEFAULT_LIMITS)

    assert summarise(violations) == summarise(tuple(reversed(violations)))
    assert summarise(()) == "within all operating limits"


def test_decision_vocabulary_matches_the_project_bible() -> None:
    """docs/00_PROJECT_BIBLE.md section 4: ACCEPT / REPRICE / REDUCE / SHIFT / REJECT."""
    assert [d.value for d in GridValidationDecision] == [
        "accept",
        "reprice",
        "reduce",
        "shift",
        "reject",
    ]
