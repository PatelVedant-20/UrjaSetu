"""Adapter-layer contracts for meter telemetry sources.

This module holds what is genuinely an *adapter* concern: how a source reports
a parse or validation failure, and how a run's results are bundled.

It deliberately defines **no normalized telemetry structure of its own**. The
one canonical contract is `app.domain.interfaces.telemetry.NormalizedReading`,
re-exported here for convenience. docs/03_REPOSITORY_STRUCTURE.md forbids
duplicate domain abstractions, and a second reading model had already drifted
from the locked one in docs/04_DATA_MODEL.md: it defaulted the power channels
to `Decimal("0.0")`, collapsing "not measured" into "measured zero", and
carried `site_id` and `voltage_pu`, which entity 10 does not define.

An adapter produces `NormalizedReading` values and satisfies
`app.domain.interfaces.telemetry.MeterReadingSource`. It never persists
anything: quality classification, duplicate handling and storage all belong to
`app.services.telemetry_service`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import TelemetrySource
from app.domain.interfaces.telemetry import MeterReadingSource, NormalizedReading

__all__ = [
    "AdapterError",
    "AdapterParseError",
    "AdapterValidationError",
    "MeterReadingSource",
    "NormalizedReading",
    "NormalizedTelemetryBatch",
    "TelemetrySource",
]


class AdapterError(Exception):
    """Base class for failures raised inside a telemetry adapter."""


class AdapterParseError(AdapterError):
    """A source record could not be parsed at all."""

    def __init__(
        self,
        message: str,
        line_number: int | None = None,
        field_name: str | None = None,
        invalid_value: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line_number = line_number
        self.field_name = field_name
        self.invalid_value = invalid_value


class AdapterValidationError(AdapterError):
    """A source record parsed, but its values cannot be accepted.

    Raised for input that is malformed as *input* — an unparseable number, a
    negative power reading, a state of charge outside 0-100. It is not used for
    data that is merely questionable: stale, duplicate and out-of-order
    readings are classified by the telemetry service, not rejected here, so the
    gap stays visible.
    """

    def __init__(
        self,
        message: str,
        line_number: int | None = None,
        field_name: str | None = None,
        invalid_value: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line_number = line_number
        self.field_name = field_name
        self.invalid_value = invalid_value


@dataclass(slots=True)
class NormalizedTelemetryBatch:
    """The result of one adapter run.

    An adapter-level bundle, not a domain type: it carries the canonical
    readings plus the diagnostics a caller needs to decide whether the run was
    healthy — which source it came from, how many records were seen, and what
    failed.
    """

    source_name: str
    readings: list[NormalizedReading] = field(default_factory=list)
    total_records: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def normalized_count(self) -> int:
        return len(self.readings)

    @property
    def error_count(self) -> int:
        return len(self.errors)
