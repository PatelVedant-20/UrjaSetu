"""Fixtures for the telemetry pipeline integration tests.

Supplies the two pieces of infrastructure the pipeline tests need:

* the registry rows their deterministic site/meter UUIDs refer to, since
  `telemetry_readings.meter_id` is a foreign key;
* a client bound to a transaction that is rolled back afterwards, so the suite
  is repeatable and leaves nothing in the development database.

Re-exported from the telemetry API test package so both suites seed the same
registry, rather than describing it twice.
"""

from __future__ import annotations

from tests.api.telemetry.conftest import (  # noqa: F401
    seeded_registry,
    telemetry_client,
)
