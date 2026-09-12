"""Phase 2: data-quality classification.

The classifier is pure, so these are true unit tests — no database, no clock.
Every case pins one rule, and the precedence tests pin the order between them,
which is what makes a stored `quality_status` reproducible
(docs/10_TESTING_AND_INTEGRATION.md: determinism).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.domain.enums import TelemetryQualityStatus, TelemetrySource
from app.domain.interfaces.telemetry import NormalizedReading
from app.domain.policies.telemetry_quality import (
    DEFAULT_STALENESS_THRESHOLD,
    SeriesContext,
    classify_reading,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
METER = uuid4()


def _reading(**overrides: object) -> NormalizedReading:
    """A well-formed, current, fully-measured reading before overrides."""
    defaults: dict[str, object] = {
        "meter_id": METER,
        "timestamp": NOW,
        "interval_start": NOW - timedelta(minutes=15),
        "interval_end": NOW,
        "source": TelemetrySource.METER,
        "generation_kw": Decimal("3.5000"),
        "load_kw": Decimal("1.2000"),
        "energy_kwh": Decimal("0.8750"),
    }
    return NormalizedReading(**{**defaults, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Each status
# ---------------------------------------------------------------------------


def test_well_formed_current_reading_is_valid() -> None:
    assessment = classify_reading(_reading(), evaluated_at=NOW)

    assert assessment.status is TelemetryQualityStatus.VALID
    assert assessment.is_usable is True


def test_source_unavailable_is_recorded() -> None:
    """An adapter that reached the source but got nothing records the gap."""
    assessment = classify_reading(_reading(source_unavailable=True), evaluated_at=NOW)

    assert assessment.status is TelemetryQualityStatus.SOURCE_UNAVAILABLE
    assert assessment.is_usable is False


def test_reading_with_no_measurement_is_missing() -> None:
    assessment = classify_reading(
        _reading(generation_kw=None, load_kw=None, energy_kwh=None), evaluated_at=NOW
    )

    assert assessment.status is TelemetryQualityStatus.MISSING


def test_negative_generation_is_invalid_value() -> None:
    assessment = classify_reading(_reading(generation_kw=Decimal("-1")), evaluated_at=NOW)

    assert assessment.status is TelemetryQualityStatus.INVALID_VALUE
    assert assessment.reason is not None
    assert "generation_kw" in assessment.reason


def test_battery_soc_above_100_is_invalid_value() -> None:
    assessment = classify_reading(_reading(battery_soc=Decimal("101")), evaluated_at=NOW)

    assert assessment.status is TelemetryQualityStatus.INVALID_VALUE


def test_battery_soc_bounds_are_inclusive() -> None:
    for soc in (Decimal("0"), Decimal("100")):
        assessment = classify_reading(_reading(battery_soc=soc), evaluated_at=NOW)
        assert assessment.status is TelemetryQualityStatus.VALID, soc


def test_interval_end_before_start_is_invalid_value() -> None:
    assessment = classify_reading(
        _reading(interval_start=NOW, interval_end=NOW - timedelta(minutes=15)), evaluated_at=NOW
    )

    assert assessment.status is TelemetryQualityStatus.INVALID_VALUE


def test_duplicate_interval_is_flagged() -> None:
    assessment = classify_reading(
        _reading(), evaluated_at=NOW, context=SeriesContext(duplicate_exists=True)
    )

    assert assessment.status is TelemetryQualityStatus.DUPLICATE


def test_reading_older_than_the_series_is_out_of_order() -> None:
    assessment = classify_reading(
        _reading(
            interval_start=NOW - timedelta(hours=2), interval_end=NOW - timedelta(minutes=105)
        ),
        evaluated_at=NOW,
        context=SeriesContext(latest_interval_start=NOW - timedelta(minutes=15)),
    )

    assert assessment.status is TelemetryQualityStatus.OUT_OF_ORDER


def test_reading_older_than_the_threshold_is_stale() -> None:
    old_end = NOW - DEFAULT_STALENESS_THRESHOLD - timedelta(minutes=1)
    assessment = classify_reading(
        _reading(interval_start=old_end - timedelta(minutes=15), interval_end=old_end),
        evaluated_at=NOW,
    )

    assert assessment.status is TelemetryQualityStatus.STALE


def test_reading_exactly_at_the_threshold_is_still_valid() -> None:
    """The boundary is exclusive, so the rule has no ambiguous instant."""
    edge = NOW - DEFAULT_STALENESS_THRESHOLD
    assessment = classify_reading(
        _reading(interval_start=edge - timedelta(minutes=15), interval_end=edge), evaluated_at=NOW
    )

    assert assessment.status is TelemetryQualityStatus.VALID


def test_default_staleness_threshold_is_fifteen_minutes() -> None:
    """Locked in docs/04_DATA_MODEL.md, entity 10: one CEA AMI metering block."""
    assert timedelta(minutes=15) == DEFAULT_STALENESS_THRESHOLD


def test_default_threshold_applied_either_side_of_the_boundary() -> None:
    """A reading one minute past the block is stale; one minute inside is not."""
    stale_end = NOW - timedelta(minutes=16)
    fresh_end = NOW - timedelta(minutes=14)

    stale = classify_reading(
        _reading(interval_start=stale_end - timedelta(minutes=15), interval_end=stale_end),
        evaluated_at=NOW,
    )
    fresh = classify_reading(
        _reading(interval_start=fresh_end - timedelta(minutes=15), interval_end=fresh_end),
        evaluated_at=NOW,
    )

    assert stale.status is TelemetryQualityStatus.STALE
    assert fresh.status is TelemetryQualityStatus.VALID


def test_staleness_threshold_is_a_parameter() -> None:
    """Callers override it; it is never read from a global."""
    end = NOW - timedelta(minutes=5)
    reading = _reading(interval_start=end - timedelta(minutes=15), interval_end=end)

    assert classify_reading(reading, evaluated_at=NOW).status is TelemetryQualityStatus.VALID
    assert (
        classify_reading(reading, evaluated_at=NOW, staleness_threshold=timedelta(minutes=1)).status
        is TelemetryQualityStatus.STALE
    )


# ---------------------------------------------------------------------------
# Precedence — one status is reachable for any input
# ---------------------------------------------------------------------------


def test_source_unavailable_outranks_every_other_condition() -> None:
    assessment = classify_reading(
        _reading(
            source_unavailable=True,
            generation_kw=Decimal("-5"),
            load_kw=None,
            energy_kwh=None,
        ),
        evaluated_at=NOW,
        context=SeriesContext(duplicate_exists=True, latest_interval_start=NOW),
    )

    assert assessment.status is TelemetryQualityStatus.SOURCE_UNAVAILABLE


def test_invalid_value_outranks_duplicate_and_stale() -> None:
    old_end = NOW - timedelta(days=1)
    assessment = classify_reading(
        _reading(
            generation_kw=Decimal("-1"),
            interval_start=old_end - timedelta(minutes=15),
            interval_end=old_end,
        ),
        evaluated_at=NOW,
        context=SeriesContext(duplicate_exists=True),
    )

    assert assessment.status is TelemetryQualityStatus.INVALID_VALUE


def test_duplicate_outranks_out_of_order() -> None:
    """A replayed reading is a duplicate, not late data."""
    assessment = classify_reading(
        _reading(interval_start=NOW - timedelta(hours=3), interval_end=NOW - timedelta(hours=2)),
        evaluated_at=NOW,
        context=SeriesContext(latest_interval_start=NOW, duplicate_exists=True),
    )

    assert assessment.status is TelemetryQualityStatus.DUPLICATE


def test_out_of_order_outranks_stale() -> None:
    old_end = NOW - timedelta(days=1)
    assessment = classify_reading(
        _reading(interval_start=old_end - timedelta(minutes=15), interval_end=old_end),
        evaluated_at=NOW,
        context=SeriesContext(latest_interval_start=NOW - timedelta(minutes=15)),
    )

    assert assessment.status is TelemetryQualityStatus.OUT_OF_ORDER


def test_classification_is_deterministic() -> None:
    reading = _reading(battery_soc=Decimal("55"))
    context = SeriesContext(latest_interval_start=NOW - timedelta(hours=1))

    first = classify_reading(reading, evaluated_at=NOW, context=context)
    second = classify_reading(reading, evaluated_at=NOW, context=context)

    assert first == second


def test_first_reading_of_a_series_is_never_out_of_order() -> None:
    assessment = classify_reading(_reading(), evaluated_at=NOW, context=SeriesContext())

    assert assessment.status is TelemetryQualityStatus.VALID


def test_zero_is_a_measurement_but_none_is_not() -> None:
    """0 kW is measured data; None means the channel is not measured at all."""
    measured_zero = classify_reading(
        _reading(generation_kw=Decimal("0"), load_kw=None, energy_kwh=None), evaluated_at=NOW
    )
    nothing = classify_reading(
        _reading(generation_kw=None, load_kw=None, energy_kwh=None), evaluated_at=NOW
    )

    assert measured_zero.status is TelemetryQualityStatus.VALID
    assert nothing.status is TelemetryQualityStatus.MISSING


# ---------------------------------------------------------------------------
# Locked vocabularies (docs/04_DATA_MODEL.md, entity 10)
# ---------------------------------------------------------------------------


def test_quality_status_vocabulary_is_locked() -> None:
    """Exactly seven states. Adding one is an architecture decision."""
    assert {status.value for status in TelemetryQualityStatus} == {
        "source_unavailable",
        "invalid_value",
        "missing",
        "duplicate",
        "out_of_order",
        "stale",
        "valid",
    }


def test_source_vocabulary_is_locked() -> None:
    """Exactly five ingestion channels, and none of them names a vendor."""
    assert {source.value for source in TelemetrySource} == {
        "meter",
        "inverter",
        "simulator",
        "import",
        "manual",
    }


def test_only_valid_is_usable() -> None:
    """Every non-valid state is excluded from last-known-valid and aggregation."""
    usable = {status for status in TelemetryQualityStatus if status.is_usable}

    assert usable == {TelemetryQualityStatus.VALID}


def test_precedence_order_is_total() -> None:
    """Every locked state is reachable, so no status is dead vocabulary.

    Builds the one input that should select each state and checks it wins.
    """
    stale_end = NOW - timedelta(minutes=30)
    cases = {
        TelemetryQualityStatus.SOURCE_UNAVAILABLE: (
            _reading(source_unavailable=True),
            SeriesContext(),
        ),
        TelemetryQualityStatus.INVALID_VALUE: (
            _reading(generation_kw=Decimal("-1")),
            SeriesContext(),
        ),
        TelemetryQualityStatus.MISSING: (
            _reading(generation_kw=None, load_kw=None, energy_kwh=None),
            SeriesContext(),
        ),
        TelemetryQualityStatus.DUPLICATE: (
            _reading(),
            SeriesContext(duplicate_exists=True),
        ),
        TelemetryQualityStatus.OUT_OF_ORDER: (
            _reading(
                interval_start=NOW - timedelta(hours=3),
                interval_end=NOW - timedelta(hours=3) + timedelta(minutes=15),
            ),
            SeriesContext(latest_interval_start=NOW),
        ),
        TelemetryQualityStatus.STALE: (
            _reading(interval_start=stale_end - timedelta(minutes=15), interval_end=stale_end),
            SeriesContext(),
        ),
        TelemetryQualityStatus.VALID: (_reading(), SeriesContext()),
    }

    for expected, (reading, context) in cases.items():
        result = classify_reading(reading, evaluated_at=NOW, context=context)
        assert result.status is expected, f"expected {expected}, got {result.status}"

    assert set(cases) == set(TelemetryQualityStatus)
