"""Telemetry data-quality classification.

Turns a `NormalizedReading` plus the context it arrived in into exactly one
`TelemetryQualityStatus`.

Pure and deterministic: no database access, no clock reads, no randomness.
`evaluated_at` and the series context are always passed in, so the same inputs
always produce the same status — required by
docs/10_TESTING_AND_INTEGRATION.md, and what makes a stored `quality_status`
explainable after the fact (docs/00_PROJECT_BIBLE.md: traceability).

The database is queried by the *service*, which packages what it found into
`SeriesContext` and hands it here. That separation is what keeps this module
testable without PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.domain.enums import TelemetryQualityStatus
from app.domain.interfaces.telemetry import NormalizedReading

# How old a reading's interval may be before it is treated as stale.
#
# LOCKED at 15 minutes (docs/04_DATA_MODEL.md, entity 10): one CEA AMI metering
# block, so a reading is stale once a whole block has passed without fresher
# data.
#
# This is a *default*, not a rule. `classify_reading` and every service entry
# point take `staleness_threshold` as a parameter and no comparison in this
# module reads the constant directly, so a later phase can apply a different
# threshold per market, feeder or asset class without touching the classifier.
DEFAULT_STALENESS_THRESHOLD = timedelta(minutes=15)

# Percent.
BATTERY_SOC_MIN = Decimal("0")
BATTERY_SOC_MAX = Decimal("100")


@dataclass(frozen=True, slots=True)
class SeriesContext:
    """What the service already knows about this meter/asset series.

    `None` on both fields means the series is empty — a first reading can be
    neither duplicate nor out-of-order.
    """

    latest_interval_start: datetime | None = None
    duplicate_exists: bool = False


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    """The classification, with the reason it came out that way."""

    status: TelemetryQualityStatus
    reason: str | None = None

    @property
    def is_usable(self) -> bool:
        return self.status.is_usable


def classify_reading(
    reading: NormalizedReading,
    *,
    evaluated_at: datetime,
    context: SeriesContext | None = None,
    staleness_threshold: timedelta = DEFAULT_STALENESS_THRESHOLD,
) -> QualityAssessment:
    """Classify one reading.

    Precedence is fixed and total, so exactly one status is reachable for any
    input:

        source_unavailable -> invalid_value -> missing -> duplicate
        -> out_of_order -> stale -> valid

    The order runs from "we have no trustworthy observation at all" to "the
    observation is fine but late". An unusable reading is never demoted to a
    milder status by a later rule.
    """
    context = context or SeriesContext()

    # 1. The adapter reached the source and it had nothing to give.
    if reading.source_unavailable:
        return QualityAssessment(
            TelemetryQualityStatus.SOURCE_UNAVAILABLE,
            "adapter reported the source as unavailable",
        )

    # 2. Something was reported but it cannot be true.
    if (invalid := _first_invalid_value(reading)) is not None:
        return QualityAssessment(TelemetryQualityStatus.INVALID_VALUE, invalid)

    # 3. Nothing was measured. A recorded gap, not a silent absence.
    if not reading.has_any_measurement:
        return QualityAssessment(
            TelemetryQualityStatus.MISSING, "no measurement present on the reading"
        )

    # 4. This interval has already been recorded for this series. Checked before
    #    ordering: a replayed reading is a duplicate, not late data.
    if context.duplicate_exists:
        return QualityAssessment(
            TelemetryQualityStatus.DUPLICATE,
            "a reading already exists for this meter, asset and interval",
        )

    # 5. It arrived after a reading that covers a later interval.
    if (
        context.latest_interval_start is not None
        and reading.interval_start < context.latest_interval_start
    ):
        return QualityAssessment(
            TelemetryQualityStatus.OUT_OF_ORDER,
            "interval_start precedes the latest stored interval for this series",
        )

    # 6. Well-formed and in order, but too old to be treated as current.
    if evaluated_at - reading.interval_end > staleness_threshold:
        return QualityAssessment(
            TelemetryQualityStatus.STALE,
            f"interval_end is older than {staleness_threshold}",
        )

    return QualityAssessment(TelemetryQualityStatus.VALID)


def _first_invalid_value(reading: NormalizedReading) -> str | None:
    """The first impossible value found, or None.

    Ordered so the message is stable for a reading with several problems.
    """
    if reading.interval_end < reading.interval_start:
        return "interval_end precedes interval_start"

    # Power and energy channels are magnitudes on a defined direction: import
    # and export are separate columns, so neither may be negative. Generation
    # cannot be negative either.
    for name in ("generation_kw", "load_kw", "grid_import_kw", "grid_export_kw", "energy_kwh"):
        value: Decimal | None = getattr(reading, name)
        if value is not None and value < 0:
            return f"{name} is negative"

    soc = reading.battery_soc
    if soc is not None and not (BATTERY_SOC_MIN <= soc <= BATTERY_SOC_MAX):
        return "battery_soc outside 0-100 percent"

    return None
