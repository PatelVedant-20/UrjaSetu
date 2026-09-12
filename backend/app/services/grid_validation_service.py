"""Grid validation orchestration.

    proposed trade -> GridValidationRequest -> GridEngine -> GridValidationResult
    -> grid_validation_runs

Owns the transaction boundary for a validation and the sequencing around a
solver. It contains **no power flow and no limits**: it assembles the network
and the injections, calls `engine.validate(...)`, applies the limits policy,
and records the outcome.

It never imports Power Grid Model, and neither may anything else outside
`app/adapters/grid/` (docs/06_OPEN_SOURCE_INTEGRATION.md section 1).

It also never approves or commits a trade. Phase 4 produces a trade with
status `proposed`; this service records a *judgement about* that trade. Acting
on the judgement — accepting, repricing, reducing, shifting — is the
grid-aware market feedback of a later phase.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models.grid import GridSnapshot, GridValidationRun
from app.domain.enums import GridValidationDecision, GridValidationStatus
from app.domain.interfaces.grid import (
    GridEngine,
    GridLimits,
    GridValidationRequest,
    GridValidationResult,
    NetworkLine,
    NetworkModel,
    NetworkNode,
    NetworkTransformer,
    NodeInjection,
)
from app.domain.policies.grid_limits import (
    DEFAULT_LIMITS,
    decide,
    describe_missing_ratings,
    effective_status,
    evaluate_metrics,
    resolve_status,
    summarise,
)
from app.repositories import (
    GridNodeRepository,
    GridSnapshotRepository,
    GridValidationRunRepository,
)
from app.services import audit_service

ZERO = Decimal("0")


class GridEngineError(UnprocessableError):
    """A grid engine failed, or returned a result the contract does not allow."""

    code = "GRID_ENGINE_FAILED"


def validate_scenario(
    session: Session,
    *,
    engine: GridEngine,
    network: NetworkModel,
    proposed_injections: Sequence[NodeInjection],
    interval_start: datetime,
    interval_end: datetime,
    baseline_injections: Sequence[NodeInjection] = (),
    limits: GridLimits = DEFAULT_LIMITS,
    trade_id: UUID | None = None,
    grid_snapshot_id: UUID | None = None,
    at: datetime | None = None,
) -> GridValidationRun:
    """Run one validation and persist it. One transaction.

    The engine is passed in rather than imported, so this function stays
    ignorant of which solver exists. Its output is validated at the boundary
    before anything is written.

    `trade_id` is optional because docs/04_DATA_MODEL.md entity 17 allows a run
    before any trade exists — a what-if scenario is a legitimate use.
    """
    if interval_end <= interval_start:
        raise UnprocessableError(
            "interval_end must be after interval_start.",
            code="GRID_INTERVAL_INVALID",
        )
    if network.is_empty:
        raise UnprocessableError("The network model contains no nodes.", code="GRID_NETWORK_EMPTY")

    request = GridValidationRequest(
        network=network,
        limits=limits,
        interval_start=interval_start,
        interval_end=interval_end,
        baseline_injections=tuple(baseline_injections),
        proposed_injections=tuple(proposed_injections),
    )

    try:
        result = engine.validate(request)
    except Exception as exc:
        # An unavailable or non-converging solver must never read as a pass.
        # The refusal is recorded so an adapter failure stays observable
        # (docs/01_FINAL_ARCHITECTURE.md).
        run = _record(
            session,
            engine=engine,
            request=request,
            result=None,
            trade_id=trade_id,
            grid_snapshot_id=grid_snapshot_id,
            reason=f"engine failure: {exc.__class__.__name__}",
            at=at,
        )
        if trade_id is not None:
            session.flush()
            audit_service.record(
                session,
                audit_service.grid_validation_recorded(
                    trade_id=trade_id,
                    grid_validation_id=run.id,
                    status=run.status,
                    decision=(
                        run.decision.value if hasattr(run.decision, "value") else str(run.decision)
                    ),
                    simulation_engine=run.simulation_engine,
                    engine_version=run.engine_version,
                    input_hash=run.input_hash,
                    min_voltage_pu=run.min_voltage_pu,
                    max_voltage_pu=run.max_voltage_pu,
                    max_line_loading_pct=run.max_line_loading_pct,
                    max_transformer_loading_pct=run.max_transformer_loading_pct,
                    reason=run.reason,
                    occurred_at=run.created_at or datetime.now(UTC),
                ),
            )
        session.commit()
        raise GridEngineError(
            f"Grid engine {engine.name!r} failed to validate the scenario.",
            details={
                "engine": engine.name,
                "reason": exc.__class__.__name__,
                "grid_validation_run_id": str(run.id),
            },
        ) from exc

    _validate_result(result, engine)

    run = _record(
        session,
        engine=engine,
        request=request,
        result=result,
        trade_id=trade_id,
        grid_snapshot_id=grid_snapshot_id,
        at=at,
    )
    if trade_id is not None:
        session.flush()
        audit_service.record(
            session,
            audit_service.grid_validation_recorded(
                trade_id=trade_id,
                grid_validation_id=run.id,
                status=run.status,
                decision=(
                    run.decision.value if hasattr(run.decision, "value") else str(run.decision)
                ),
                simulation_engine=run.simulation_engine,
                engine_version=run.engine_version,
                input_hash=run.input_hash,
                min_voltage_pu=run.min_voltage_pu,
                max_voltage_pu=run.max_voltage_pu,
                max_line_loading_pct=run.max_line_loading_pct,
                max_transformer_loading_pct=run.max_transformer_loading_pct,
                reason=run.reason,
                occurred_at=run.created_at or datetime.now(UTC),
            ),
        )
    session.commit()
    session.refresh(run)
    return run


def validate_trade(
    session: Session,
    *,
    engine: GridEngine,
    trade_id: UUID,
    seller_node_id: UUID,
    buyer_node_id: UUID,
    quantity_kwh: Decimal,
    delivery_start: datetime,
    delivery_end: datetime,
    feeder_id: str | None = None,
    baseline_injections: Sequence[NodeInjection] = (),
    limits: GridLimits = DEFAULT_LIMITS,
    at: datetime | None = None,
) -> GridValidationRun:
    """Judge whether a proposed trade is safe for the network.

    This is the market-to-grid boundary. It takes the identifiers a Phase 4
    trade carries — not the ORM object — so the market and the grid stay
    decoupled, and converts the traded *energy* into the *power* a solver needs
    exactly once, through `NodeInjection.from_energy`.

    The seller injects and the buyer withdraws the same power, which is what
    makes this a transfer across the network rather than new net generation.
    """
    interval = delivery_end - delivery_start
    if interval <= timedelta(0):
        raise UnprocessableError(
            "delivery_end must be after delivery_start.", code="GRID_INTERVAL_INVALID"
        )
    if quantity_kwh <= ZERO:
        raise UnprocessableError(
            "quantity_kwh must be greater than zero.", code="GRID_QUANTITY_INVALID"
        )

    injection = NodeInjection.from_energy(
        node_id=seller_node_id, energy_kwh=quantity_kwh, interval=interval
    )
    withdrawal = NodeInjection(node_id=buyer_node_id, active_power_kw=-injection.active_power_kw)

    network = build_network(session, feeder_id=feeder_id)
    snapshot = GridSnapshotRepository(session).latest_for_feeder(feeder_id) if feeder_id else None

    return validate_scenario(
        session,
        engine=engine,
        network=network,
        proposed_injections=(injection, withdrawal),
        interval_start=delivery_start,
        interval_end=delivery_end,
        baseline_injections=baseline_injections,
        limits=limits,
        trade_id=trade_id,
        grid_snapshot_id=snapshot.id if snapshot is not None else None,
        at=at,
    )


def build_network(
    session: Session, *, feeder_id: str | None = None, version: str = "phase-1-twin"
) -> NetworkModel:
    """Project the stored digital twin into the grid contract.

    Reads `grid_nodes`, which Phase 1 already owns — there is one topology
    model, not a second one for the solver.

    Lines and transformers are derived from the node hierarchy: a node with a
    parent implies a connection to it, and a `transformer` node implies a
    transformer on that connection. Each edge carries the child node's
    `rated_capacity_kw`, which is the rating of exactly that element.

    A node with no recorded rating produces an edge with `rating_kw=None`.
    That is propagated rather than defaulted: a made-up rating would produce a
    confident loading percentage from an invented denominator, and the honest
    answer is that this element's thermal state is unknown.
    """
    nodes = GridNodeRepository(session).list(limit=10_000)
    if feeder_id is not None:
        nodes = [node for node in nodes if node.feeder_id == feeder_id]

    ratings = {node.id: node.rated_capacity_kw for node in nodes}
    network_nodes = tuple(
        NetworkNode(
            node_id=node.id,
            node_type=node.node_type,
            nominal_voltage_kv=node.nominal_voltage_kv,
            parent_node_id=node.parent_node_id,
            feeder_id=node.feeder_id,
        )
        for node in nodes
    )
    known = {node.node_id for node in network_nodes}

    lines: list[NetworkLine] = []
    transformers: list[NetworkTransformer] = []
    for node in network_nodes:
        if node.parent_node_id is None or node.parent_node_id not in known:
            continue
        if node.node_type.value == "transformer":
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
        nodes=network_nodes,
        lines=tuple(lines),
        transformers=tuple(transformers),
    )


def record_snapshot(
    session: Session,
    *,
    feeder_id: str | None,
    captured_at: datetime,
    system_load_kw: Decimal | None = None,
    generation_kw: Decimal | None = None,
    transformer_loading_pct: Decimal | None = None,
    max_line_loading_pct: Decimal | None = None,
    min_voltage_pu: Decimal | None = None,
    max_voltage_pu: Decimal | None = None,
) -> GridSnapshot:
    """Record observed network state. One transaction."""
    snapshot = GridSnapshot(
        feeder_id=feeder_id,
        captured_at=captured_at,
        system_load_kw=system_load_kw,
        generation_kw=generation_kw,
        transformer_loading_pct=transformer_loading_pct,
        max_line_loading_pct=max_line_loading_pct,
        min_voltage_pu=min_voltage_pu,
        max_voltage_pu=max_voltage_pu,
    )
    GridSnapshotRepository(session).add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_validation_run(session: Session, validation_id: UUID) -> GridValidationRun:
    run = GridValidationRunRepository(session).get(validation_id)
    if run is None:
        raise NotFoundError(
            "Grid validation run not found.",
            code="GRID_VALIDATION_NOT_FOUND",
            details={"id": str(validation_id)},
        )
    return run


def latest_for_trade(session: Session, trade_id: UUID) -> GridValidationRun | None:
    """The most recent judgement about a trade, or None if never validated."""
    return GridValidationRunRepository(session).latest_for_trade(trade_id)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def request_fingerprint(request: GridValidationRequest) -> str:
    """A stable hash of everything that determines the outcome.

    Stored as `grid_validation_runs.input_hash`, so a result can be tied to its
    exact inputs and an identical scenario recognised. Sorted and rendered as
    text, because dictionary and float ordering are not stable enough to hash.
    """
    payload = {
        "network_version": request.network.version,
        "nodes": sorted(str(node.node_id) for node in request.network.nodes),
        "limits": [
            str(request.limits.min_voltage_pu),
            str(request.limits.max_voltage_pu),
            str(request.limits.max_line_loading_pct),
            str(request.limits.max_transformer_loading_pct),
        ],
        "interval": [request.interval_start.isoformat(), request.interval_end.isoformat()],
        "injections": sorted(
            f"{i.node_id}:{i.active_power_kw}" for i in request.combined_injections
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _record(
    session: Session,
    *,
    engine: GridEngine,
    request: GridValidationRequest,
    result: GridValidationResult | None,
    trade_id: UUID | None,
    grid_snapshot_id: UUID | None,
    reason: str | None = None,
    at: datetime | None = None,
) -> GridValidationRun:
    """Persist a validation outcome, including a failure.

    A failed engine still produces a row: an unavailable solver is a fact about
    this trade, and silently having no record would let the same trade be
    retried as though it had never been questioned.
    """
    if result is None:
        # `unknown`, not `unsafe`: nothing was observed about this network. The
        # trade is blocked either way, but the record says which happened.
        run = GridValidationRun(
            trade_id=trade_id,
            grid_snapshot_id=grid_snapshot_id,
            simulation_engine=engine.name,
            engine_version=engine.engine_version,
            input_hash=request_fingerprint(request),
            status=GridValidationStatus.UNKNOWN,
            decision=GridValidationDecision.REJECT,
            reason=reason,
            created_at=at or datetime.now(UTC),
        )
        GridValidationRunRepository(session).add(run)
        return run

    unrated = request.network.unrated_elements
    caused = result.caused_violations
    status = effective_status(
        resolve_status(result.status, unrated_elements=unrated), caused_violations=caused
    )
    decision = decide(status=status, caused_violations=caused)

    if reason is not None:
        explanation = reason
    elif status is GridValidationStatus.UNKNOWN and unrated:
        explanation = describe_missing_ratings(unrated)
    else:
        explanation = summarise(caused or result.violations)

    run = GridValidationRun(
        trade_id=trade_id,
        grid_snapshot_id=grid_snapshot_id,
        simulation_engine=result.engine,
        engine_version=result.engine_version,
        input_hash=request_fingerprint(request),
        status=status,
        min_voltage_pu=result.metrics.min_voltage_pu,
        max_voltage_pu=result.metrics.max_voltage_pu,
        max_line_loading_pct=result.metrics.max_line_loading_pct,
        max_transformer_loading_pct=result.metrics.max_transformer_loading_pct,
        decision=decision,
        reason=explanation,
        created_at=at or datetime.now(UTC),
    )
    GridValidationRunRepository(session).add(run)
    return run


def _validate_result(result: GridValidationResult, engine: GridEngine) -> None:
    """Check an engine's output before trusting it.

    The important case is the last one: an engine that claims a network is safe
    while reporting metrics that breach the limits has contradicted itself, and
    accepting that would let a trade through on the strength of a bug.
    """
    if not result.engine:
        raise GridEngineError(
            "Engine returned a result with no engine identifier.",
            details={"engine": engine.name},
        )
    for violation in result.violations:
        if violation.limit < ZERO:
            raise GridEngineError(
                "Engine reported a violation against a negative limit.",
                details={"engine": engine.name},
            )
    metrics = result.metrics
    if (
        metrics.min_voltage_pu is not None
        and metrics.max_voltage_pu is not None
        and metrics.min_voltage_pu > metrics.max_voltage_pu
    ):
        raise GridEngineError(
            "Engine reported a minimum voltage above its maximum.",
            details={"engine": engine.name},
        )


def cross_check(result: GridValidationResult, limits: GridLimits) -> tuple[str, ...]:
    """Disagreements between an engine's `safe` flag and its own metrics.

    Not raised on: an engine has per-element detail the aggregate metrics do
    not, so it may legitimately know about a violation these numbers cannot
    show. Reported so a disagreement is visible rather than silent.
    """
    derived = evaluate_metrics(result.metrics, limits)
    if derived and result.status is GridValidationStatus.SAFE:
        return tuple(
            f"engine reported safe but {v.violation_type.value} "
            f"({v.observed} vs limit {v.limit})"
            for v in derived
        )
    return ()
