"""Phase 5 service and persistence tests.

Drives `app.services.grid_validation_service` end to end against a real
PostgreSQL database, through stand-in engines rather than a power-flow solver:
the service must be able to drive *anything* satisfying `GridEngine`, including
one that fails or contradicts itself.

Covers the behaviours the Phase 5 brief requires before handoff — a safe
network, each violation class, baseline versus proposed attribution, a
deterministic result, the market-to-grid boundary, and the guarantee that a
validation never approves or commits a trade.
"""

from __future__ import annotations

import ast
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models import GridNode
from app.db.models.grid import GridValidationRun
from app.domain.enums import (
    GridNodeType,
    GridValidationDecision,
    GridValidationStatus,
    GridViolationType,
)
from app.domain.interfaces.grid import (
    GridLimits,
    GridMetrics,
    GridValidationResult,
    NetworkModel,
    NodeInjection,
)
from app.domain.policies.grid_limits import DEFAULT_LIMITS
from app.repositories import GridSnapshotRepository, GridValidationRunRepository
from app.services import grid_validation_service as service
from app.services.grid_validation_service import GridEngineError

from .conftest import (
    DELIVERY_END,
    DELIVERY_START,
    FEEDER,
    HEALTHY,
    NOW,
    FailingGridEngine,
    StubGridEngine,
    violation,
)

ONE_HOUR = timedelta(hours=1)


def _run_scenario(
    db_session: Session,
    engine: StubGridEngine,
    *,
    network: NetworkModel,
    injections: tuple[NodeInjection, ...] = (),
    limits: GridLimits = DEFAULT_LIMITS,
    trade_id: uuid.UUID | None = None,
) -> GridValidationRun:
    return service.validate_scenario(
        db_session,
        engine=engine,
        network=network,
        proposed_injections=injections,
        interval_start=DELIVERY_START,
        interval_end=DELIVERY_END,
        limits=limits,
        trade_id=trade_id,
    )


# ---------------------------------------------------------------------------
# 1. Safe network
# ---------------------------------------------------------------------------


def test_safe_network_is_accepted_and_recorded(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """Voltages mid-band and thermal headroom to spare: accept."""
    engine = StubGridEngine()
    run = _run_scenario(db_session, engine, network=simple_network)

    assert run.id is not None
    assert run.status is GridValidationStatus.SAFE
    assert run.decision is GridValidationDecision.ACCEPT
    assert run.simulation_engine == "stub-grid"
    assert run.engine_version == "1.0.0"
    assert run.reason == "within all operating limits"
    assert run.min_voltage_pu == Decimal("0.99")
    assert run.max_voltage_pu == Decimal("1.01")
    assert run.max_line_loading_pct == Decimal("40")
    assert run.max_transformer_loading_pct == Decimal("55")


def test_engine_receives_the_interval_and_limits_it_was_given(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """The service assembles the request; it does not reinterpret it."""
    engine = StubGridEngine()
    tight = GridLimits(
        min_voltage_pu=Decimal("0.97"),
        max_voltage_pu=Decimal("1.03"),
        max_line_loading_pct=Decimal("80"),
        max_transformer_loading_pct=Decimal("80"),
    )
    _run_scenario(db_session, engine, network=simple_network, limits=tight)

    assert len(engine.calls) == 1
    request = engine.calls[0]
    assert request.limits == tight
    assert request.interval_start == DELIVERY_START
    assert request.interval_end == DELIVERY_END
    assert request.interval == ONE_HOUR


# ---------------------------------------------------------------------------
# 2-4. Each violation class rejects
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "metrics", "observed", "limit"),
    [
        (
            GridViolationType.UNDER_VOLTAGE,
            GridMetrics(min_voltage_pu=Decimal("0.91"), max_voltage_pu=Decimal("1.00")),
            "0.91",
            "0.94",
        ),
        (
            GridViolationType.OVER_VOLTAGE,
            GridMetrics(min_voltage_pu=Decimal("1.00"), max_voltage_pu=Decimal("1.09")),
            "1.09",
            "1.06",
        ),
        (
            GridViolationType.LINE_OVERLOAD,
            GridMetrics(max_line_loading_pct=Decimal("127.5")),
            "127.5",
            "100",
        ),
        (
            GridViolationType.TRANSFORMER_OVERLOAD,
            GridMetrics(max_transformer_loading_pct=Decimal("118")),
            "118",
            "100",
        ),
    ],
    ids=["under_voltage", "over_voltage", "line_overload", "transformer_overload"],
)
def test_each_violation_class_rejects_the_trade(
    db_session: Session,
    simple_network: NetworkModel,
    kind: GridViolationType,
    metrics: GridMetrics,
    observed: str,
    limit: str,
) -> None:
    """Every documented violation type blocks the trade and is explained."""
    engine = StubGridEngine(
        metrics=metrics,
        violations=(violation(kind, observed, limit),),
        status=GridValidationStatus.UNSAFE,
    )
    run = _run_scenario(db_session, engine, network=simple_network)

    assert run.status is GridValidationStatus.UNSAFE
    assert run.decision is GridValidationDecision.REJECT
    assert run.reason is not None
    assert kind.value in run.reason
    assert observed in run.reason


def test_violation_margin_measures_the_distance_past_the_limit() -> None:
    """Reported so a later phase can size a reduction rather than guess one."""
    over = violation(GridViolationType.LINE_OVERLOAD, "127.5", "100")
    under = violation(GridViolationType.UNDER_VOLTAGE, "0.91", "0.94")

    assert over.margin == Decimal("27.5")
    assert under.margin == Decimal("0.03")


# ---------------------------------------------------------------------------
# 5. Baseline versus proposed
# ---------------------------------------------------------------------------


def test_preexisting_violation_does_not_block_an_unrelated_trade(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """A feeder already over its limit is not this trade's fault.

    The engine reports the same violation before and after, so the trade caused
    nothing and the network is still called safe with respect to it.
    """
    already_there = violation(GridViolationType.LINE_OVERLOAD, "104", "100")
    engine = StubGridEngine(
        metrics=HEALTHY,
        violations=(already_there,),
        baseline_violations=(already_there,),
        status=GridValidationStatus.SAFE,
    )
    run = _run_scenario(db_session, engine, network=simple_network)

    assert run.decision is GridValidationDecision.ACCEPT
    assert run.status is GridValidationStatus.SAFE


def test_trade_that_causes_a_new_violation_is_rejected(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """One pre-existing problem, one new one: only the new one is attributable."""
    already_there = violation(GridViolationType.LINE_OVERLOAD, "104", "100")
    caused = violation(GridViolationType.OVER_VOLTAGE, "1.08", "1.06")
    engine = StubGridEngine(
        metrics=GridMetrics(max_voltage_pu=Decimal("1.08"), max_line_loading_pct=Decimal("104")),
        violations=(already_there, caused),
        baseline_violations=(already_there,),
        status=GridValidationStatus.SAFE,
    )
    run = _run_scenario(db_session, engine, network=simple_network)

    assert run.decision is GridValidationDecision.REJECT
    assert run.status is GridValidationStatus.UNSAFE
    assert run.reason is not None
    assert "over_voltage" in run.reason
    assert "line_overload" not in run.reason, "A pre-existing fault is not the trade's reason"


def test_unsafe_network_is_never_accepted_on_the_grounds_it_was_already_broken(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """`safe=False` with nothing attributable still rejects."""
    engine = StubGridEngine(metrics=HEALTHY, violations=(), status=GridValidationStatus.UNSAFE)
    run = _run_scenario(db_session, engine, network=simple_network)

    assert run.decision is GridValidationDecision.REJECT
    assert run.status is GridValidationStatus.UNSAFE


# ---------------------------------------------------------------------------
# 6. Deterministic result
# ---------------------------------------------------------------------------


def test_identical_scenarios_fingerprint_identically(
    db_session: Session, simple_network: NetworkModel
) -> None:
    engine = StubGridEngine()
    first = _run_scenario(db_session, engine, network=simple_network)
    second = _run_scenario(db_session, engine, network=simple_network)

    assert first.id != second.id, "Each attempt is its own record"
    assert first.input_hash == second.input_hash
    assert len(first.input_hash) == 64


def test_different_injections_fingerprint_differently(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """Otherwise a re-run with more power would be mistaken for a repeat."""
    node_id = simple_network.nodes[-1].node_id
    engine = StubGridEngine()

    small = _run_scenario(
        db_session,
        engine,
        network=simple_network,
        injections=(NodeInjection(node_id=node_id, active_power_kw=Decimal("5")),),
    )
    large = _run_scenario(
        db_session,
        engine,
        network=simple_network,
        injections=(NodeInjection(node_id=node_id, active_power_kw=Decimal("50")),),
    )

    assert small.input_hash != large.input_hash


def test_fingerprint_ignores_the_order_injections_arrive_in(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """The same scenario described in a different order is the same scenario."""
    first_node, second_node = (n.node_id for n in simple_network.nodes)
    a = NodeInjection(node_id=first_node, active_power_kw=Decimal("7"))
    b = NodeInjection(node_id=second_node, active_power_kw=Decimal("-7"))
    engine = StubGridEngine()

    forward = _run_scenario(db_session, engine, network=simple_network, injections=(a, b))
    reverse = _run_scenario(db_session, engine, network=simple_network, injections=(b, a))

    assert forward.input_hash == reverse.input_hash


# ---------------------------------------------------------------------------
# 7. An engine failure never reads as a pass
# ---------------------------------------------------------------------------


def test_engine_failure_is_recorded_as_unknown_not_as_unsafe(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """A solver that will not converge has not approved anything — and has not
    condemned anything either.

    The trade is blocked exactly as an unsafe network would block it, but the
    record says the grid was never actually cleared, which is a different fact
    from a feeder found to be overloaded.
    """
    engine = FailingGridEngine()

    with pytest.raises(GridEngineError) as caught:
        _run_scenario(db_session, engine, network=simple_network)

    run_id = uuid.UUID(caught.value.details["grid_validation_run_id"])
    run = service.get_validation_run(db_session, run_id)
    assert run.status is GridValidationStatus.UNKNOWN
    assert run.status.was_evaluated is False
    assert run.status.permits_trade is False
    assert run.decision is GridValidationDecision.REJECT
    assert run.reason is not None
    assert "RuntimeError" in run.reason
    assert caught.value.code == "GRID_ENGINE_FAILED"


def test_result_without_an_engine_identifier_is_refused(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """An unattributable result cannot be audited, so it is not stored."""

    class AnonymousEngine(StubGridEngine):
        def validate(self, request: object) -> GridValidationResult:  # type: ignore[override]
            return GridValidationResult(
                engine="",
                engine_version="1.0.0",
                status=GridValidationStatus.SAFE,
                metrics=HEALTHY,
            )

    with pytest.raises(GridEngineError):
        _run_scenario(db_session, AnonymousEngine(), network=simple_network)


def test_result_with_inverted_voltage_range_is_refused(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """A minimum above a maximum is a defect in the engine, not a finding."""
    engine = StubGridEngine(
        metrics=GridMetrics(min_voltage_pu=Decimal("1.05"), max_voltage_pu=Decimal("0.95"))
    )
    with pytest.raises(GridEngineError):
        _run_scenario(db_session, engine, network=simple_network)


def test_empty_network_is_refused_before_any_engine_runs(db_session: Session) -> None:
    engine = StubGridEngine()
    with pytest.raises(UnprocessableError) as caught:
        _run_scenario(db_session, engine, network=NetworkModel(version="empty"))

    assert caught.value.code == "GRID_NETWORK_EMPTY"
    assert engine.calls == [], "No solver should be asked about a network with no nodes"


def test_backwards_interval_is_refused(db_session: Session, simple_network: NetworkModel) -> None:
    engine = StubGridEngine()
    with pytest.raises(UnprocessableError) as caught:
        service.validate_scenario(
            db_session,
            engine=engine,
            network=simple_network,
            proposed_injections=(),
            interval_start=DELIVERY_END,
            interval_end=DELIVERY_START,
        )
    assert caught.value.code == "GRID_INTERVAL_INVALID"


# ---------------------------------------------------------------------------
# 8. Cross-check: engine's own metrics versus its verdict
# ---------------------------------------------------------------------------


def test_cross_check_reports_an_engine_that_contradicts_its_own_metrics() -> None:
    """Not raised on — reported, so the disagreement is visible."""
    result = GridValidationResult(
        engine="stub-grid",
        engine_version="1.0.0",
        status=GridValidationStatus.SAFE,
        metrics=GridMetrics(max_line_loading_pct=Decimal("150")),
    )
    disagreements = service.cross_check(result, DEFAULT_LIMITS)

    assert len(disagreements) == 1
    assert "line_overload" in disagreements[0]


def test_cross_check_is_silent_when_metrics_agree_with_the_verdict() -> None:
    result = GridValidationResult(
        engine="stub-grid",
        engine_version="1.0.0",
        status=GridValidationStatus.SAFE,
        metrics=HEALTHY,
    )
    assert service.cross_check(result, DEFAULT_LIMITS) == ()


# ---------------------------------------------------------------------------
# 9. The market-to-grid boundary
# ---------------------------------------------------------------------------


def test_validate_trade_converts_energy_to_power_exactly_once(
    db_session: Session, make_feeder: object
) -> None:
    """100 kWh delivered over one hour is 100 kW, and the seller injects it."""
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    seller, buyer = nodes[2], nodes[3]
    engine = StubGridEngine()
    trade_id = uuid.uuid4()

    run = service.validate_trade(
        db_session,
        engine=engine,
        trade_id=trade_id,
        seller_node_id=seller.id,
        buyer_node_id=buyer.id,
        quantity_kwh=Decimal("100"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )

    request = engine.calls[0]
    by_node = {i.node_id: i.active_power_kw for i in request.proposed_injections}
    assert by_node[seller.id] == Decimal("100")
    assert by_node[buyer.id] == Decimal("-100")
    assert sum(by_node.values()) == Decimal("0"), "A transfer is not new net generation"
    assert run.trade_id == trade_id


def test_validate_trade_halves_the_interval_and_doubles_the_power(
    db_session: Session, make_feeder: object
) -> None:
    """The same 100 kWh over 30 minutes is 200 kW — kW and kWh never mix."""
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    seller, buyer = nodes[2], nodes[3]
    engine = StubGridEngine()

    service.validate_trade(
        db_session,
        engine=engine,
        trade_id=uuid.uuid4(),
        seller_node_id=seller.id,
        buyer_node_id=buyer.id,
        quantity_kwh=Decimal("100"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_START + timedelta(minutes=30),
        feeder_id=FEEDER,
    )

    by_node = {i.node_id: i.active_power_kw for i in engine.calls[0].proposed_injections}
    assert by_node[seller.id] == Decimal("200")


def test_node_injection_refuses_a_zero_length_interval() -> None:
    """Dividing energy by no time is undefined, not infinite."""
    with pytest.raises(ValueError, match="positive duration"):
        NodeInjection.from_energy(
            node_id=uuid.uuid4(), energy_kwh=Decimal("10"), interval=timedelta(0)
        )


def test_validate_trade_refuses_a_non_positive_quantity(
    db_session: Session, make_feeder: object
) -> None:
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    with pytest.raises(UnprocessableError) as caught:
        service.validate_trade(
            db_session,
            engine=StubGridEngine(),
            trade_id=uuid.uuid4(),
            seller_node_id=nodes[2].id,
            buyer_node_id=nodes[3].id,
            quantity_kwh=Decimal("0"),
            delivery_start=DELIVERY_START,
            delivery_end=DELIVERY_END,
            feeder_id=FEEDER,
        )
    assert caught.value.code == "GRID_QUANTITY_INVALID"


def test_validate_trade_attaches_the_latest_snapshot_of_the_feeder(
    db_session: Session, make_feeder: object
) -> None:
    """The judgement is tied to the network state it was made against."""
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    service.record_snapshot(db_session, feeder_id=FEEDER, captured_at=NOW - timedelta(hours=2))
    current = service.record_snapshot(db_session, feeder_id=FEEDER, captured_at=NOW)

    run = service.validate_trade(
        db_session,
        engine=StubGridEngine(),
        trade_id=uuid.uuid4(),
        seller_node_id=nodes[2].id,
        buyer_node_id=nodes[3].id,
        quantity_kwh=Decimal("10"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )

    assert run.grid_snapshot_id == current.id


def test_validation_never_approves_or_commits_a_trade(
    db_session: Session, make_feeder: object
) -> None:
    """Phase 5 records a judgement; acting on it belongs to a later phase.

    A run that accepts must leave no committed trade behind and set no
    commitment timestamp — the run is the only thing written.
    """
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    trade_id = uuid.uuid4()

    run = service.validate_trade(
        db_session,
        engine=StubGridEngine(),
        trade_id=trade_id,
        seller_node_id=nodes[2].id,
        buyer_node_id=nodes[3].id,
        quantity_kwh=Decimal("10"),
        delivery_start=DELIVERY_START,
        delivery_end=DELIVERY_END,
        feeder_id=FEEDER,
    )

    assert run.decision is GridValidationDecision.ACCEPT
    assert not hasattr(run, "committed_at")
    assert service.latest_for_trade(db_session, trade_id) is not None


def test_grid_service_never_imports_market_persistence() -> None:
    """It takes the identifiers a trade carries, never the trade row itself.

    Checked on imports rather than on source text, so the service is free to
    explain the market boundary in prose while depending on none of it.
    """
    tree = ast.parse(Path(service.__file__).read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(
        name == "app.db.models.market" or name.startswith("app.services.market")
        for name in imported
    ), f"Grid validation must not reach into market persistence: {sorted(imported)}"


# ---------------------------------------------------------------------------
# 10. Building the network from the Phase 1 twin
# ---------------------------------------------------------------------------


def test_build_network_projects_the_twin_without_remodelling_it(
    db_session: Session, make_feeder: object
) -> None:
    """Topology comes from `grid_nodes`; the solver gets a plain contract."""
    nodes = make_feeder(FEEDER)  # type: ignore[operator]
    network = service.build_network(db_session, feeder_id=FEEDER)

    assert len(network.nodes) == 4
    assert network.node_ids == {n.id for n in nodes}
    assert not network.is_empty

    # substation -> transformer is a transformer; transformer -> points are lines.
    assert len(network.transformers) == 1
    assert network.transformers[0].transformer_id == nodes[1].id
    assert network.transformers[0].from_node_id == nodes[0].id
    assert len(network.lines) == 2
    assert {line.from_node_id for line in network.lines} == {nodes[1].id}


def test_build_network_filters_to_one_feeder(db_session: Session, make_feeder: object) -> None:
    """A validation of one feeder must not drag in a neighbouring one."""
    mine = make_feeder(FEEDER)  # type: ignore[operator]
    make_feeder("FEEDER-OTHER")  # type: ignore[operator]

    network = service.build_network(db_session, feeder_id=FEEDER)
    assert network.node_ids == {n.id for n in mine}


def test_build_network_omits_edges_to_nodes_outside_the_selection(
    db_session: Session, make_feeder: object
) -> None:
    """A dangling parent is not an edge; it is a node that was filtered out."""
    make_feeder(FEEDER)  # type: ignore[operator]
    orphan_parent = GridNode(
        external_ref=f"sub-{uuid.uuid4().hex[:8]}",
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11.0000"),
        feeder_id="FEEDER-ELSEWHERE",
    )
    db_session.add(orphan_parent)
    db_session.flush()
    child = GridNode(
        external_ref=f"cp-{uuid.uuid4().hex[:8]}",
        node_type=GridNodeType.CONNECTION_POINT,
        nominal_voltage_kv=Decimal("0.4000"),
        parent_node_id=orphan_parent.id,
        feeder_id=FEEDER,
    )
    db_session.add(child)
    db_session.flush()

    network = service.build_network(db_session, feeder_id=FEEDER)
    assert child.id in network.node_ids
    assert all(line.to_node_id != child.id for line in network.lines)


# ---------------------------------------------------------------------------
# 11. Persistence and retrieval
# ---------------------------------------------------------------------------


def test_snapshot_records_missing_measurements_as_null_not_zero(db_session: Session) -> None:
    """An unmonitored feeder must not read as an idle one."""
    snapshot = service.record_snapshot(
        db_session,
        feeder_id=FEEDER,
        captured_at=NOW,
        system_load_kw=Decimal("120.5"),
    )

    assert snapshot.system_load_kw == Decimal("120.5")
    assert snapshot.generation_kw is None
    assert snapshot.min_voltage_pu is None


def test_latest_snapshot_is_chosen_by_observation_time_not_write_time(
    db_session: Session,
) -> None:
    """A late-arriving snapshot of an earlier moment is not current."""
    service.record_snapshot(db_session, feeder_id=FEEDER, captured_at=NOW)
    service.record_snapshot(db_session, feeder_id=FEEDER, captured_at=NOW - timedelta(days=1))

    latest = GridSnapshotRepository(db_session).latest_for_feeder(FEEDER)
    assert latest is not None
    assert latest.captured_at == NOW


def test_snapshots_are_listed_within_the_requested_window(db_session: Session) -> None:
    for offset in (-2, -1, 0):
        service.record_snapshot(
            db_session, feeder_id=FEEDER, captured_at=NOW + timedelta(hours=offset)
        )

    found = GridSnapshotRepository(db_session).list_for_feeder(
        FEEDER, start=NOW - timedelta(hours=1), end=NOW
    )
    assert [s.captured_at for s in found] == [NOW - timedelta(hours=1), NOW]


def test_validation_history_for_a_trade_is_kept_not_overwritten(
    db_session: Session, simple_network: NetworkModel
) -> None:
    """A decision stays explainable after the network changes."""
    trade_id = uuid.uuid4()
    _run_scenario(db_session, StubGridEngine(), network=simple_network, trade_id=trade_id)
    _run_scenario(
        db_session,
        StubGridEngine(
            metrics=GridMetrics(max_line_loading_pct=Decimal("140")),
            violations=(violation(GridViolationType.LINE_OVERLOAD, "140", "100"),),
            status=GridValidationStatus.UNSAFE,
        ),
        network=simple_network,
        trade_id=trade_id,
    )

    history = GridValidationRunRepository(db_session).list_for_trade(trade_id)
    assert len(history) == 2
    assert [r.decision for r in history] == [
        GridValidationDecision.ACCEPT,
        GridValidationDecision.REJECT,
    ]
    latest = service.latest_for_trade(db_session, trade_id)
    assert latest is not None
    assert latest.decision is GridValidationDecision.REJECT


def test_a_previous_run_of_an_identical_scenario_can_be_found(
    db_session: Session, simple_network: NetworkModel
) -> None:
    run = _run_scenario(db_session, StubGridEngine(), network=simple_network)
    found = GridValidationRunRepository(db_session).find_by_input_hash(run.input_hash)

    assert found is not None
    assert found.input_hash == run.input_hash


def test_unknown_validation_run_raises_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as caught:
        service.get_validation_run(db_session, uuid.uuid4())
    assert caught.value.code == "GRID_VALIDATION_NOT_FOUND"


def test_latest_for_trade_is_none_when_never_validated(db_session: Session) -> None:
    assert service.latest_for_trade(db_session, uuid.uuid4()) is None


def test_database_refuses_a_run_that_is_safe_but_not_accepted(db_session: Session) -> None:
    """The two columns cannot drift: a rejected trade can never look approved."""
    db_session.add(
        GridValidationRun(
            trade_id=uuid.uuid4(),
            simulation_engine="stub-grid",
            input_hash="0" * 64,
            status=GridValidationStatus.SAFE,
            decision=GridValidationDecision.REJECT,
        )
    )
    with pytest.raises(IntegrityError, match="decision_agrees_with_safety"):
        db_session.flush()


def test_database_refuses_an_unsafe_run_recorded_as_accepted(db_session: Session) -> None:
    db_session.add(
        GridValidationRun(
            trade_id=uuid.uuid4(),
            simulation_engine="stub-grid",
            input_hash="0" * 64,
            status=GridValidationStatus.UNSAFE,
            decision=GridValidationDecision.ACCEPT,
        )
    )
    with pytest.raises(IntegrityError, match="decision_agrees_with_safety"):
        db_session.flush()
