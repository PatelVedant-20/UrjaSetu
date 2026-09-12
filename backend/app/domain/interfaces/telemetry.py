"""The normalized telemetry contract.

This is the boundary every telemetry source meets:

    adapter -> NormalizedReading -> telemetry service -> repository -> PostgreSQL

Nothing here knows about CSV, SunSpec, Modbus, a vendor API or the simulator.
An adapter's only obligation is to produce `NormalizedReading` values; it never
touches a session, a model or SQL (docs/06_OPEN_SOURCE_INTEGRATION.md keeps
external libraries behind the adapter boundary, and
docs/03_REPOSITORY_STRUCTURE.md keeps persistence out of adapters).

Units are fixed by docs/00_PROJECT_BIBLE.md section 6 and are **not converted**
anywhere in the domain or persistence layers: power is kW, energy is kWh,
battery state of charge is percent, and every timestamp is timezone-aware UTC.
Converting from a device's native units is the adapter's job, so that a wrong
conversion is traceable to one adapter rather than hidden in shared code.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.enums import TelemetrySource


@dataclass(frozen=True, slots=True)
class NormalizedReading:
    """One normalized measurement, independent of where it came from.

    Mirrors `telemetry_readings` in docs/04_DATA_MODEL.md. No field is invented
    and none is omitted.

    Every measurement is optional and `None` means **not measured by this
    device**, which is deliberately different from `Decimal("0")` meaning
    *measured as zero*. Collapsing the two would make a missing channel
    indistinguishable from a genuine zero, and data quality is the entire point
    of this phase.

    Frozen: a reading is an observation, so nothing downstream may edit one
    after an adapter has produced it.
    """

    meter_id: UUID
    timestamp: datetime
    interval_start: datetime
    interval_end: datetime
    source: TelemetrySource

    energy_asset_id: UUID | None = None

    # kW
    generation_kw: Decimal | None = None
    load_kw: Decimal | None = None
    grid_import_kw: Decimal | None = None
    grid_export_kw: Decimal | None = None
    # kWh over [interval_start, interval_end)
    energy_kwh: Decimal | None = None
    # percent, 0-100
    battery_soc: Decimal | None = None

    # Set by an adapter that was reachable but had nothing to report — a failed
    # poll, a device offline. It is how "the source said nothing" reaches the
    # classifier as a fact rather than as an absence
    # (docs/01_FINAL_ARCHITECTURE.md: adapter failures stay observable).
    source_unavailable: bool = False

    @property
    def measurements(self) -> tuple[Decimal | None, ...]:
        """The measured channels, in a fixed order."""
        return (
            self.generation_kw,
            self.load_kw,
            self.grid_import_kw,
            self.grid_export_kw,
            self.energy_kwh,
            self.battery_soc,
        )

    @property
    def has_any_measurement(self) -> bool:
        return any(value is not None for value in self.measurements)


class MeterReadingSource(Protocol):
    """What a telemetry adapter must implement.

    Deliberately tiny. A simulator, a CSV importer, a SunSpec client and an AMI
    feed all satisfy it, and the service depends on this Protocol rather than
    on any of them.

    Implementations live under `app/adapters/meter/` and `app/adapters/inverter/`
    and are owned by the agent assigned that adapter; this declaration is the
    contract they implement, not an implementation.
    """

    def read(self, *, since: datetime | None = None) -> Iterable[NormalizedReading]:
        """Yield normalized readings, oldest first.

        Raising is acceptable for a transport failure. To report "reachable but
        no data", yield readings with `source_unavailable=True` instead, so the
        gap is recorded rather than lost.
        """
        ...
