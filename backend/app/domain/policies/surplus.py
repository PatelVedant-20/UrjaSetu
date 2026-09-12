"""Expected-surplus calculation.

    expected_surplus = forecast_generation - forecast_consumption

Deliberately *outside* the forecasting algorithm. A provider predicts what a
site will generate and what it will consume; deciding what that implies about
sellable energy is a business rule, and keeping it separate means the rule can
be tested, reviewed and changed without retraining or replacing a model — and
that swapping the provider cannot quietly change what "surplus" means.

Pure and deterministic: plain values in, plain values out, no database access
and no clock reads (docs/10_TESTING_AND_INTEGRATION.md: determinism).

This phase carries no pricing and no order creation. Surplus is an energy
quantity, nothing more.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SurplusPoint:
    """Expected surplus over one interval.

    `surplus_kw` is signed: positive means the site is expected to export,
    negative that it must import. Clamping to zero here would throw away the
    deficit, which the market needs in order to size buy orders in Phase 4.
    """

    interval_start: datetime
    interval_end: datetime
    generation_kw: Decimal | None
    load_kw: Decimal | None
    surplus_kw: Decimal | None

    @property
    def is_exporting(self) -> bool:
        return self.surplus_kw is not None and self.surplus_kw > ZERO

    @property
    def exportable_kw(self) -> Decimal:
        """Surplus available to sell — never negative, never unknown."""
        if self.surplus_kw is None or self.surplus_kw < ZERO:
            return ZERO
        return self.surplus_kw


@dataclass(frozen=True, slots=True)
class SurplusWindow:
    """Expected surplus across a horizon."""

    points: Sequence[SurplusPoint]

    @property
    def total_exportable_kwh(self) -> Decimal:
        """Energy a site could offer over the window, in kWh.

        Each interval's exportable power is weighted by its own duration, so a
        window of unevenly spaced points still totals correctly. Intervals with
        no usable prediction contribute nothing rather than being guessed at.
        """
        total = ZERO
        for point in self.points:
            hours = Decimal((point.interval_end - point.interval_start).total_seconds()) / Decimal(
                3600
            )
            total += point.exportable_kw * hours
        return total

    @property
    def has_exportable_energy(self) -> bool:
        return self.total_exportable_kwh > ZERO


def calculate_surplus(
    *,
    generation: Iterable[tuple[datetime, datetime, Decimal | None]],
    consumption: Iterable[tuple[datetime, datetime, Decimal | None]],
) -> SurplusWindow:
    """Pair a generation forecast with a consumption forecast, interval by interval.

    Each input is `(interval_start, interval_end, predicted_kw)`. Intervals are
    matched on `interval_start`, so the two forecasts need not arrive in the
    same order — but they must share a bucket grid, which the orchestration
    service guarantees by requesting both at the same resolution.

    An interval present in only one forecast is still returned, with the
    missing side `None` and the surplus `None`. A one-sided prediction is not
    a surplus of the other side's magnitude, and silently treating the absent
    channel as zero would invent export capacity that was never forecast.
    """
    gen = {start: (end, value) for start, end, value in generation}
    load = {start: (end, value) for start, end, value in consumption}

    points: list[SurplusPoint] = []
    for start in sorted(gen.keys() | load.keys()):
        gen_end, gen_kw = gen.get(start, (None, None))
        load_end, load_kw = load.get(start, (None, None))
        end = gen_end or load_end
        if end is None:  # pragma: no cover - unreachable: start came from a key
            continue

        surplus = None if gen_kw is None or load_kw is None else gen_kw - load_kw
        points.append(
            SurplusPoint(
                interval_start=start,
                interval_end=end,
                generation_kw=gen_kw,
                load_kw=load_kw,
                surplus_kw=surplus,
            )
        )

    return SurplusWindow(points=points)
