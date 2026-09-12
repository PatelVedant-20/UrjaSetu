"""The grid validation contract.

This is the stable boundary between UrjaSetu and whatever solves the power
flow:

    proposed trade -> GridValidationRequest -> GridEngine -> GridValidationResult

Nothing here knows how a load flow is computed. Power Grid Model is the
selected engine (docs/06_OPEN_SOURCE_INTEGRATION.md section 1), but it lives
behind `app/adapters/grid/power_grid_model_adapter.py` and **no other layer may
import it**. A future GridLAB-D or an analytical approximation satisfies the
same Protocol, so the solver can be replaced without touching the validation
service, the schema, the market or the API.

An engine is **pure**. It receives a network and a set of injections and
returns metrics and violations. It never opens a session, reads a row, or
knows that PostgreSQL, FastAPI, a market or a ledger exist. That is what makes
a validation reproducible from stored inputs (docs/00_PROJECT_BIBLE.md:
traceability) and deterministic — which matters more here than anywhere else,
because docs/00_PROJECT_BIBLE.md is explicit that grid safety is decided by a
deterministic analysis layer and never by a model that might guess.

Units, stated once and never mixed (docs/00_PROJECT_BIBLE.md section 6):

* **kW** — every power quantity, including injections and ratings.
* **kWh** — energy, which is what a *market trade* is denominated in.
* **per-unit (pu)** — voltage, relative to a node's nominal voltage.
* **percent** — line and transformer loading, relative to rating.

Energy becomes power exactly once, in `NodeInjection.from_energy`, and never
implicitly. A trade of E kWh delivered evenly over an interval of H hours is an
average injection of E / H kW; that even-delivery assumption is the modelling
choice, and it is made in one visible place rather than scattered.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.enums import GridNodeType, GridValidationStatus, GridViolationType

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Network topology
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NetworkNode:
    """A bus in the digital twin.

    Mirrors `grid_nodes` (docs/04_DATA_MODEL.md entity 4) as plain values. The
    persistence model is deliberately not handed to an engine: a solver that
    took the ORM class could lazy-load a relationship mid-solve.
    """

    node_id: UUID
    node_type: GridNodeType
    nominal_voltage_kv: Decimal
    parent_node_id: UUID | None = None
    feeder_id: str | None = None


@dataclass(frozen=True, slots=True)
class NetworkLine:
    """A conductor between two nodes."""

    line_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    # Continuous current-carrying capacity, expressed as the power the line may
    # carry before it is at 100 % loading.
    #
    # `None` means the twin does not record a rating for this conductor, which
    # is not the same as a rating of zero: loading cannot be computed for it at
    # all, and a validation that depends on it can only conclude UNKNOWN.
    rating_kw: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NetworkTransformer:
    """A transformer between two voltage levels."""

    transformer_id: UUID
    from_node_id: UUID
    to_node_id: UUID
    # Nameplate continuous rating. `None` means unknown — see `NetworkLine`.
    rating_kw: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NetworkModel:
    """The topology a validation runs against.

    `version` identifies which build of the twin was used, so a stored
    validation stays explainable after the network is edited.
    """

    version: str
    nodes: Sequence[NetworkNode] = field(default_factory=tuple)
    lines: Sequence[NetworkLine] = field(default_factory=tuple)
    transformers: Sequence[NetworkTransformer] = field(default_factory=tuple)

    @property
    def node_ids(self) -> frozenset[UUID]:
        return frozenset(node.node_id for node in self.nodes)

    @property
    def is_empty(self) -> bool:
        return not self.nodes

    @property
    def unrated_elements(self) -> tuple[UUID, ...]:
        """Lines and transformers the twin records no rating for.

        Loading is a percentage *of a rating*; without one there is no
        percentage to compute and no overload to detect. Naming them lets a
        result say precisely what it could not assess.
        """
        return tuple(
            [line.line_id for line in self.lines if line.rating_kw is None]
            + [tx.transformer_id for tx in self.transformers if tx.rating_kw is None]
        )

    @property
    def has_complete_ratings(self) -> bool:
        """Whether every edge carries a rating, so thermal limits are decidable.

        A network with no edges at all is trivially complete: there is nothing
        whose loading could be unknown.
        """
        return not self.unrated_elements


# ---------------------------------------------------------------------------
# Injections
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NodeInjection:
    """Net power at one node, in kW.

    Sign convention, fixed once: **positive is generation into the network,
    negative is consumption from it.** Every producer of an injection must obey
    it, because a sign error here is indistinguishable from a real reverse flow
    and would silently invert a congestion result.
    """

    node_id: UUID
    active_power_kw: Decimal

    @classmethod
    def from_energy(
        cls, *, node_id: UUID, energy_kwh: Decimal, interval: timedelta
    ) -> NodeInjection:
        """Convert an energy commitment into an equivalent power injection.

        The one place kWh becomes kW. A trade of `energy_kwh` delivered evenly
        across `interval` is an average injection of `energy_kwh / hours` kW.

        Even delivery is an explicit modelling assumption: it understates a
        peaky delivery profile, which is why validation uses the interval the
        market actually committed to rather than a longer, flattering one.
        """
        hours = Decimal(interval.total_seconds()) / Decimal(3600)
        if hours <= ZERO:
            raise ValueError("interval must be a positive duration to convert kWh to kW")
        return cls(node_id=node_id, active_power_kw=energy_kwh / hours)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GridLimits:
    """The thresholds a network is judged against.

    Passed in rather than read from a global, and never hard-coded in the
    market service: a feeder in a dense urban network and one on a long rural
    spur are not held to the same numbers.
    """

    min_voltage_pu: Decimal
    max_voltage_pu: Decimal
    max_line_loading_pct: Decimal
    max_transformer_loading_pct: Decimal


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GridValidationRequest:
    """Everything an engine needs to judge a proposed trade.

    Self-contained on purpose: a request can be logged and replayed to explain
    why a trade was accepted or rejected months later.

    The comparison is explicitly baseline-versus-proposed. `baseline_injections`
    is the network as it already stands; `proposed_injections` is what the
    trade would add on top. An engine solves both, so a violation that already
    existed is not blamed on this trade.
    """

    network: NetworkModel
    limits: GridLimits
    interval_start: datetime
    interval_end: datetime
    baseline_injections: Sequence[NodeInjection] = field(default_factory=tuple)
    proposed_injections: Sequence[NodeInjection] = field(default_factory=tuple)

    @property
    def interval(self) -> timedelta:
        return self.interval_end - self.interval_start

    @property
    def combined_injections(self) -> tuple[NodeInjection, ...]:
        """Baseline plus proposal, summed per node.

        Provided here so every engine combines them the same way; two engines
        disagreeing about superposition would make results incomparable.
        """
        totals: dict[UUID, Decimal] = {}
        for injection in (*self.baseline_injections, *self.proposed_injections):
            totals[injection.node_id] = (
                totals.get(injection.node_id, ZERO) + injection.active_power_kw
            )
        return tuple(
            NodeInjection(node_id=node_id, active_power_kw=total)
            for node_id, total in sorted(totals.items(), key=lambda item: str(item[0]))
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GridViolation:
    """One breached constraint.

    Carries the measured value and the limit it broke, so a caller can see how
    far over the line the network went without the engine grading it. That is
    also what a later remediation phase needs in order to decide how much to
    reduce or shift.
    """

    violation_type: GridViolationType
    # The node, line or transformer at fault.
    element_id: UUID | None
    observed: Decimal
    limit: Decimal
    # Free text from the engine, for diagnosis only — never parsed.
    detail: str | None = None

    @property
    def margin(self) -> Decimal:
        """How far past the limit the observation went.

        Positive for an exceeded ceiling and for a breached floor alike, so
        severity can be compared across violation types.
        """
        if self.violation_type is GridViolationType.UNDER_VOLTAGE:
            return self.limit - self.observed
        return self.observed - self.limit


@dataclass(frozen=True, slots=True)
class GridMetrics:
    """The normalised numbers every engine must report.

    Exactly the quantities docs/06_OPEN_SOURCE_INTEGRATION.md names as the
    adapter's normalised output, and exactly what `grid_validation_runs`
    (docs/04_DATA_MODEL.md entity 17) stores.
    """

    min_voltage_pu: Decimal | None = None
    max_voltage_pu: Decimal | None = None
    max_line_loading_pct: Decimal | None = None
    max_transformer_loading_pct: Decimal | None = None


@dataclass(frozen=True, slots=True)
class GridValidationResult:
    """What an engine returns.

    `status` is the engine's finding about the network. It is **not** a
    decision about the trade: translating a finding into accept/reject — and,
    later, into reprice/reduce/shift — is the validation service's and the
    market's business, not the solver's.

    It is a three-state value rather than a boolean, so an engine that could
    not reach a trustworthy answer can say exactly that. An engine returns
    `UNKNOWN` when it solved nothing it can stand behind — a non-converged
    power flow it chose to report rather than raise, or a network missing the
    ratings its thermal checks depend on. An engine must never return `SAFE`
    for a network it did not actually clear.

    `engine` and `engine_version` identify what produced this, so a stored
    validation can always be attributed to a specific solver at a specific
    version.
    """

    engine: str
    engine_version: str
    status: GridValidationStatus
    metrics: GridMetrics
    violations: Sequence[GridViolation] = field(default_factory=tuple)
    # Violations the baseline already had, before the proposed trade. Reported
    # separately so an existing problem is not attributed to this trade.
    baseline_violations: Sequence[GridViolation] = field(default_factory=tuple)

    @property
    def safe(self) -> bool:
        """Whether the network was positively shown to be within limits.

        Derived, never stored: `UNKNOWN` reads as not-safe here, which is the
        conservative direction, while `status` keeps the distinction that a
        boolean throws away.
        """
        return self.status.permits_trade

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)

    @property
    def caused_violations(self) -> tuple[GridViolation, ...]:
        """Violations this trade introduced, excluding pre-existing ones.

        Compared on type and element: a trade that worsens an already-violated
        element is still that element's existing problem, and attributing it to
        the trade would make every order on a stressed feeder unsellable.
        """
        already = {(v.violation_type, v.element_id) for v in self.baseline_violations}
        return tuple(v for v in self.violations if (v.violation_type, v.element_id) not in already)


@runtime_checkable
class GridEngine(Protocol):
    """What a power-flow implementation must provide.

    Implementations live in `app/adapters/grid/` and are owned by the agent
    assigned that adapter. This declaration is the contract they implement, not
    an implementation.

    Deliberately tiny: one identity pair and one pure method. Anything an
    engine needs beyond that — solver tolerances, iteration limits, a cached
    network build — is its own constructor's business, invisible to the
    validation service.
    """

    @property
    def name(self) -> str:
        """Stable identifier, persisted as `grid_validation_runs.simulation_engine`."""
        ...

    @property
    def engine_version(self) -> str:
        """Version of the solver or its wrapper.

        Change it whenever the same request could produce a different result,
        so a past validation stays explainable.
        """
        ...

    def validate(self, request: GridValidationRequest) -> GridValidationResult:
        """Solve the network and report metrics and violations.

        Must be deterministic: the same request yields the same result. Grid
        safety is decided by deterministic analysis, never by a model that
        might guess (docs/00_PROJECT_BIBLE.md: deterministic safety).

        Must solve the baseline **and** baseline-plus-proposal, so
        `baseline_violations` distinguishes an existing problem from one this
        trade would cause.

        Must never report `SAFE` for a network it did not actually clear.
        Raise for a genuine solver failure, or return `UNKNOWN` — either is
        recorded honestly; a false `SAFE` is not recoverable.

        Raise on failure rather than returning `safe=True` with empty metrics.
        A solver that did not converge has not shown the network is safe, and
        an unavailable grid engine must never read as a pass — the validation
        service records the failure and refuses the trade.
        """
        ...
