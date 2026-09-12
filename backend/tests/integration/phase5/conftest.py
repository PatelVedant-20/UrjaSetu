"""Phase 5 fixtures.

The engines here are **stand-ins for the contract, not power-flow solvers**.
The real solver is Power Grid Model behind
`app/adapters/grid/power_grid_model_adapter.py`, owned by the agent assigned
that adapter; these exist only to prove the validation service can drive
anything satisfying `GridEngine`, including one that fails or contradicts
itself.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.models import GridNode
from app.domain.enums import GridNodeType, GridValidationStatus, GridViolationType
from app.domain.interfaces.grid import (
    GridMetrics,
    GridValidationRequest,
    GridValidationResult,
    GridViolation,
    NetworkModel,
    NetworkNode,
)

NOW = datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
DELIVERY_START = NOW
DELIVERY_END = NOW + timedelta(hours=1)
FEEDER = "FEEDER-P5"

# A healthy network: voltage mid-band, plenty of thermal headroom.
HEALTHY = GridMetrics(
    min_voltage_pu=Decimal("0.99"),
    max_voltage_pu=Decimal("1.01"),
    max_line_loading_pct=Decimal("40"),
    max_transformer_loading_pct=Decimal("55"),
)


class StubGridEngine:
    """Returns whatever metrics and violations it was constructed with.

    Satisfies `GridEngine` structurally — no inheritance — which is the point:
    an adapter only has to match the shape.
    """

    def __init__(
        self,
        *,
        name: str = "stub-grid",
        engine_version: str = "1.0.0",
        metrics: GridMetrics = HEALTHY,
        violations: tuple[GridViolation, ...] = (),
        baseline_violations: tuple[GridViolation, ...] = (),
        status: GridValidationStatus | None = None,
    ) -> None:
        self._name = name
        self._version = engine_version
        self._metrics = metrics
        self._violations = violations
        self._baseline_violations = baseline_violations
        self._status = status
        self.calls: list[GridValidationRequest] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def engine_version(self) -> str:
        return self._version

    def validate(self, request: GridValidationRequest) -> GridValidationResult:
        self.calls.append(request)
        status = self._status
        if status is None:
            status = GridValidationStatus.UNSAFE if self._violations else GridValidationStatus.SAFE
        return GridValidationResult(
            engine=self._name,
            engine_version=self._version,
            status=status,
            metrics=self._metrics,
            violations=self._violations,
            baseline_violations=self._baseline_violations,
        )


class FailingGridEngine(StubGridEngine):
    """A solver that does not converge, to prove failures never read as a pass."""

    def validate(self, request: GridValidationRequest) -> GridValidationResult:
        raise RuntimeError("power flow did not converge")


def violation(
    kind: GridViolationType,
    observed: str,
    limit: str,
    element_id: uuid.UUID | None = None,
) -> GridViolation:
    return GridViolation(
        violation_type=kind,
        element_id=element_id,
        observed=Decimal(observed),
        limit=Decimal(limit),
    )


# Ratings for the test feeder, in kW. A 250 kVA distribution transformer and
# LV service conductors are ordinary sizes for an Indian LV feeder, which keeps
# the loading arithmetic in these tests recognisable.
TRANSFORMER_RATING_KW = Decimal("250.0000")
SERVICE_LINE_RATING_KW = Decimal("60.0000")


@pytest.fixture
def make_feeder(db_session: Session) -> Callable[..., list[GridNode]]:
    """A substation -> transformer -> connection-point chain in the real twin.

    Uses the Phase 1 `grid_nodes` topology rather than a second model.

    Rated by default, because a rated feeder is the normal case and an unrated
    one is a specific condition worth asking for: pass `rated=False` to get the
    twin as it looked before capacity was recorded, where thermal limits cannot
    be assessed at all.
    """

    def _make(feeder_id: str = FEEDER, *, rated: bool = True) -> list[GridNode]:
        substation = GridNode(
            external_ref=f"sub-{uuid.uuid4().hex[:8]}",
            node_type=GridNodeType.SUBSTATION,
            nominal_voltage_kv=Decimal("11.0000"),
            feeder_id=feeder_id,
        )
        db_session.add(substation)
        db_session.flush()

        transformer = GridNode(
            external_ref=f"tx-{uuid.uuid4().hex[:8]}",
            node_type=GridNodeType.TRANSFORMER,
            nominal_voltage_kv=Decimal("0.4000"),
            parent_node_id=substation.id,
            feeder_id=feeder_id,
            rated_capacity_kw=TRANSFORMER_RATING_KW if rated else None,
        )
        db_session.add(transformer)
        db_session.flush()

        points = []
        for _ in range(2):
            point = GridNode(
                external_ref=f"cp-{uuid.uuid4().hex[:8]}",
                node_type=GridNodeType.CONNECTION_POINT,
                nominal_voltage_kv=Decimal("0.4000"),
                parent_node_id=transformer.id,
                feeder_id=feeder_id,
                rated_capacity_kw=SERVICE_LINE_RATING_KW if rated else None,
            )
            db_session.add(point)
            points.append(point)
        db_session.flush()
        return [substation, transformer, *points]

    return _make


@pytest.fixture
def simple_network() -> NetworkModel:
    """A two-node network, for contract tests that need no database."""
    substation = NetworkNode(
        node_id=uuid.uuid4(),
        node_type=GridNodeType.SUBSTATION,
        nominal_voltage_kv=Decimal("11"),
    )
    point = NetworkNode(
        node_id=uuid.uuid4(),
        node_type=GridNodeType.CONNECTION_POINT,
        nominal_voltage_kv=Decimal("0.4"),
        parent_node_id=substation.node_id,
    )
    return NetworkModel(version="test", nodes=(substation, point))
