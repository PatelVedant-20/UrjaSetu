"""Grid operating limits and the decision they imply.

Two separate concerns, kept together because both are pure policy:

* **What counts as a violation** — the thresholds a network is judged against.
* **What a finding means for a trade** — turning "the network is unsafe" into
  accept or reject.

Neither belongs in a solver: an engine reports what the physics says, and this
module decides what the platform does about it. Neither belongs in the market
service either, which is why limits are values passed around rather than
constants buried in an `if`.

Pure and deterministic: plain values in, plain values out, no I/O and no clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from app.domain.enums import (
    GridValidationDecision,
    GridValidationStatus,
    GridViolationType,
)
from app.domain.interfaces.grid import GridLimits, GridMetrics, GridViolation

# Default operating envelope for a low-voltage distribution feeder.
#
# ±6 % voltage and 100 % thermal loading. Indian LV distribution is commonly
# held to a ±6 % band, and a conductor or transformer at 100 % of nameplate is
# by definition at its continuous limit. These are *defaults*, not rules:
# `GridLimits` is a parameter on every call, so a feeder with a different
# operating envelope is configured, not special-cased.
DEFAULT_LIMITS = GridLimits(
    min_voltage_pu=Decimal("0.94"),
    max_voltage_pu=Decimal("1.06"),
    max_line_loading_pct=Decimal("100"),
    max_transformer_loading_pct=Decimal("100"),
)


def evaluate_metrics(metrics: GridMetrics, limits: GridLimits) -> tuple[GridViolation, ...]:
    """Derive violations from normalised metrics.

    Provided so every engine and every test judges the same numbers the same
    way. An engine may report violations it found itself — it has per-element
    detail this function cannot see — but the aggregate metrics it returns must
    never disagree with this, or a stored validation would contradict its own
    recorded numbers.

    Element ids are `None` here: metrics are network-wide extremes, and which
    specific line was worst is detail only the engine holds.
    """
    violations: list[GridViolation] = []

    if metrics.min_voltage_pu is not None and metrics.min_voltage_pu < limits.min_voltage_pu:
        violations.append(
            GridViolation(
                violation_type=GridViolationType.UNDER_VOLTAGE,
                element_id=None,
                observed=metrics.min_voltage_pu,
                limit=limits.min_voltage_pu,
                detail="network minimum voltage below the operating band",
            )
        )
    if metrics.max_voltage_pu is not None and metrics.max_voltage_pu > limits.max_voltage_pu:
        violations.append(
            GridViolation(
                violation_type=GridViolationType.OVER_VOLTAGE,
                element_id=None,
                observed=metrics.max_voltage_pu,
                limit=limits.max_voltage_pu,
                detail="network maximum voltage above the operating band",
            )
        )
    if (
        metrics.max_line_loading_pct is not None
        and metrics.max_line_loading_pct > limits.max_line_loading_pct
    ):
        violations.append(
            GridViolation(
                violation_type=GridViolationType.LINE_OVERLOAD,
                element_id=None,
                observed=metrics.max_line_loading_pct,
                limit=limits.max_line_loading_pct,
                detail="line loading above its continuous rating",
            )
        )
    if (
        metrics.max_transformer_loading_pct is not None
        and metrics.max_transformer_loading_pct > limits.max_transformer_loading_pct
    ):
        violations.append(
            GridViolation(
                violation_type=GridViolationType.TRANSFORMER_OVERLOAD,
                element_id=None,
                observed=metrics.max_transformer_loading_pct,
                limit=limits.max_transformer_loading_pct,
                detail="transformer loading above its continuous rating",
            )
        )

    return tuple(violations)


def resolve_status(
    reported: GridValidationStatus, *, unrated_elements: Sequence[UUID]
) -> GridValidationStatus:
    """Reconcile an engine's verdict with what the twin could actually support.

    An engine can only judge thermal loading where a rating exists. If any line
    or transformer in the network has none, a `SAFE` verdict covers less than
    it appears to — the voltages were checked, the overloads were not — and is
    downgraded to `UNKNOWN`.

    `UNSAFE` is left alone: the engine found a real breach, incomplete ratings
    or not, and the trade is blocked either way. `UNKNOWN` stays `UNKNOWN`.
    Nothing here ever upgrades a status; missing information only ever
    subtracts confidence (docs/00_PROJECT_BIBLE.md: deterministic safety).
    """
    if reported is GridValidationStatus.SAFE and unrated_elements:
        return GridValidationStatus.UNKNOWN
    return reported


def effective_status(
    status: GridValidationStatus, *, caused_violations: Sequence[GridViolation]
) -> GridValidationStatus:
    """The status to record, once the trade's own effect is accounted for.

    An engine judges the *network*. It may find the network as a whole within
    limits while this particular trade still introduces a breach — a violation
    that is absent from the baseline and present with the proposal. Storing
    that run as `safe` would be false: it is safe without the trade, which is
    not what the record is about.

    `UNKNOWN` survives unchanged. A network nobody could assess does not become
    assessable because the trade happened to cause nothing visible.
    """
    if status is GridValidationStatus.UNKNOWN:
        return GridValidationStatus.UNKNOWN
    if caused_violations:
        return GridValidationStatus.UNSAFE
    return status


def decide(
    *, status: GridValidationStatus, caused_violations: Sequence[GridViolation]
) -> GridValidationDecision:
    """Turn an engine's finding into a decision about the trade.

    This phase decides only between the two ends of the documented vocabulary
    (docs/00_PROJECT_BIBLE.md section 4). Choosing a remedy — reprice, reduce,
    shift — needs to know what the market could offer instead, which is the
    grid-aware feedback of a later phase; it will consume the violations
    recorded here.

    A trade is accepted only when the network was positively shown to be safe
    *and* the trade caused nothing. A pre-existing violation does not block an
    unrelated trade, but a network the engine calls unsafe is never accepted on
    the grounds that the problem was already there — and a network nobody could
    assess is never accepted at all.
    """
    if status.permits_trade and not caused_violations:
        return GridValidationDecision.ACCEPT
    return GridValidationDecision.REJECT


def describe_missing_ratings(unrated_elements: Sequence[UUID]) -> str:
    """The reason string for a validation that could not assess thermal limits."""
    count = len(unrated_elements)
    noun = "element has" if count == 1 else "elements have"
    return f"thermal limits not assessable: {count} network {noun} no recorded rating"


def summarise(violations: Sequence[GridViolation]) -> str:
    """A short, stable reason string for `grid_validation_runs.reason`.

    Sorted by type so the same set of violations always reads the same way,
    which keeps stored reasons comparable between runs.
    """
    if not violations:
        return "within all operating limits"

    parts = [
        f"{v.violation_type.value} ({v.observed} vs limit {v.limit})"
        for v in sorted(violations, key=lambda v: v.violation_type.value)
    ]
    return "; ".join(parts)
