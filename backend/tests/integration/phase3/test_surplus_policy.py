"""Phase 3: surplus calculation.

The policy is pure, so these are true unit tests — no database, no provider,
no clock. Surplus is deliberately independent of the forecasting algorithm, and
that independence is what these tests pin.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domain.policies.surplus import SurplusPoint, calculate_surplus

T0 = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
IV = timedelta(minutes=15)


def _series(*values: Decimal | None, start: datetime = T0, step: timedelta = IV):  # type: ignore[no-untyped-def]
    return [(start + step * i, start + step * (i + 1), v) for i, v in enumerate(values)]


def test_surplus_is_generation_minus_consumption() -> None:
    window = calculate_surplus(
        generation=_series(Decimal("5.0")), consumption=_series(Decimal("2.0"))
    )

    assert len(window.points) == 1
    assert window.points[0].surplus_kw == Decimal("3.0")


def test_deficit_is_reported_as_a_negative_surplus() -> None:
    """Signed, not clamped: Phase 4 sizes buy orders from the deficit."""
    window = calculate_surplus(
        generation=_series(Decimal("1.0")), consumption=_series(Decimal("4.0"))
    )

    point = window.points[0]
    assert point.surplus_kw == Decimal("-3.0")
    assert point.is_exporting is False
    # Nothing is sellable, though.
    assert point.exportable_kw == Decimal("0")


def test_exact_balance_is_zero_surplus() -> None:
    window = calculate_surplus(
        generation=_series(Decimal("3.0")), consumption=_series(Decimal("3.0"))
    )

    assert window.points[0].surplus_kw == Decimal("0")
    assert window.points[0].is_exporting is False


def test_intervals_are_paired_by_start() -> None:
    """Order of arrival must not matter."""
    generation = _series(Decimal("5.0"), Decimal("6.0"))
    consumption = list(reversed(_series(Decimal("1.0"), Decimal("2.0"))))

    window = calculate_surplus(generation=generation, consumption=consumption)

    assert [p.surplus_kw for p in window.points] == [Decimal("4.0"), Decimal("4.0")]


def test_points_are_returned_in_chronological_order() -> None:
    window = calculate_surplus(
        generation=list(reversed(_series(Decimal("1"), Decimal("2"), Decimal("3")))),
        consumption=_series(Decimal("0"), Decimal("0"), Decimal("0")),
    )

    starts = [p.interval_start for p in window.points]
    assert starts == sorted(starts)


def test_one_sided_interval_yields_no_surplus() -> None:
    """A missing side is unknown, not zero.

    Treating an absent consumption forecast as zero would invent export
    capacity that was never predicted.
    """
    window = calculate_surplus(generation=_series(Decimal("5.0")), consumption=[])

    point = window.points[0]
    assert point.generation_kw == Decimal("5.0")
    assert point.load_kw is None
    assert point.surplus_kw is None
    assert point.exportable_kw == Decimal("0")


def test_unpredicted_channel_yields_no_surplus() -> None:
    """An explicit `None` prediction behaves the same as an absent interval."""
    window = calculate_surplus(generation=_series(None), consumption=_series(Decimal("2.0")))

    assert window.points[0].surplus_kw is None


def test_total_exportable_energy_weights_each_interval_by_its_duration() -> None:
    """kW over a quarter hour is a quarter of a kWh."""
    window = calculate_surplus(
        generation=_series(Decimal("4.0"), Decimal("8.0")),
        consumption=_series(Decimal("0"), Decimal("0")),
    )

    # 4 kW * 0.25 h + 8 kW * 0.25 h = 3 kWh
    assert window.total_exportable_kwh == Decimal("3")
    assert window.has_exportable_energy is True


def test_deficits_do_not_subtract_from_exportable_energy() -> None:
    """An hour of import does not cancel an hour of export you could sell."""
    window = calculate_surplus(
        generation=_series(Decimal("4.0"), Decimal("0")),
        consumption=_series(Decimal("0"), Decimal("4.0")),
    )

    assert window.total_exportable_kwh == Decimal("1")


def test_unevenly_spaced_intervals_total_correctly() -> None:
    generation = [
        (T0, T0 + timedelta(minutes=15), Decimal("4.0")),
        (T0 + timedelta(minutes=15), T0 + timedelta(minutes=75), Decimal("2.0")),
    ]
    consumption = [
        (T0, T0 + timedelta(minutes=15), Decimal("0")),
        (T0 + timedelta(minutes=15), T0 + timedelta(minutes=75), Decimal("0")),
    ]

    window = calculate_surplus(generation=generation, consumption=consumption)

    # 4 kW * 0.25 h + 2 kW * 1 h = 3 kWh
    assert window.total_exportable_kwh == Decimal("3")


def test_empty_forecasts_produce_an_empty_window() -> None:
    window = calculate_surplus(generation=[], consumption=[])

    assert window.points == []
    assert window.total_exportable_kwh == Decimal("0")
    assert window.has_exportable_energy is False


def test_calculation_is_deterministic() -> None:
    generation = _series(Decimal("5.0"), Decimal("6.0"))
    consumption = _series(Decimal("1.0"), Decimal("2.0"))

    first = calculate_surplus(generation=generation, consumption=consumption)
    second = calculate_surplus(generation=generation, consumption=consumption)

    assert first == second


def test_surplus_point_exportable_never_negative() -> None:
    point = SurplusPoint(
        interval_start=T0,
        interval_end=T0 + IV,
        generation_kw=Decimal("0"),
        load_kw=Decimal("5"),
        surplus_kw=Decimal("-5"),
    )

    assert point.exportable_kw == Decimal("0")
