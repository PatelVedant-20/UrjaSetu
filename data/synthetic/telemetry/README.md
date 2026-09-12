# Synthetic Telemetry Data Quality Fixtures

This directory contains deterministic synthetic telemetry datasets representing critical data-quality conditions for **UrjaSetu Phase 2**.

## Schema Specification

Every reading strictly adheres to `docs/04_DATA_MODEL.md` entity 10 (`telemetry_readings`):

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Unique reading identifier |
| `meter_id` | UUID | Foreign key to `meters.id` |
| `energy_asset_id` | UUID (nullable) | Foreign key to `energy_assets.id` |
| `timestamp` | ISO-8601 UTC string | Recording / packet timestamp |
| `interval_start` | ISO-8601 UTC string | Beginning of measurement interval |
| `interval_end` | ISO-8601 UTC string | End of measurement interval |
| `generation_kw` | Float / Decimal | Power generated (kW) |
| `load_kw` | Float / Decimal | Power consumed (kW) |
| `grid_import_kw` | Float / Decimal | Power imported from grid (kW) |
| `grid_export_kw` | Float / Decimal | Power exported to grid (kW) |
| `energy_kwh` | Float / Decimal | Net energy over interval (kWh) |
| `battery_soc` | Float / Decimal (nullable) | Battery state of charge (0.0 - 100.0%) |
| `quality_status` | String | Data quality classification (`valid`, `stale`, `out_of_order`, `duplicate`, `invalid`) |
| `source` | String | Data source identifier (e.g. `smart_meter`, `inverter`, `simulator`) |

## Fixture Files & Quality Scenarios

| Scenario | File | Description |
|---|---|---|
| **Valid** | [`valid_telemetry.json`](./valid_telemetry.json) | Continuous, monotonically increasing 15-minute intervals with balanced power flow. |
| **Missing** | [`missing_telemetry.json`](./missing_telemetry.json) | Communication packet drop resulting in a 30-minute blackout window (09:30Z - 10:00Z). |
| **Stale** | [`stale_telemetry.json`](./stale_telemetry.json) | Frozen sensor readings past the 15-minute freshness threshold (150 min staleness). |
| **Out-of-Order** | [`out_of_order_telemetry.json`](./out_of_order_telemetry.json) | Non-chronological arrival sequence testing timeseries sorting and ingestion buffer reassembly. |
| **Duplicate** | [`duplicate_telemetry.json`](./duplicate_telemetry.json) | Retransmission duplicates (identical payload) and timestamp collisions (conflicting measurements). |
| **Invalid Measurement** | [`invalid_measurement_telemetry.json`](./invalid_measurement_telemetry.json) | Negative generation, capacity breach (95 kW on 5 kW system), negative load, invalid SOC, inverted interval. |
| **Manifest** | [`telemetry_manifest.json`](./telemetry_manifest.json) | Machine-readable index linking all scenarios and expected test assertions. |

## Referential Integrity

All fixtures reference valid Phase-1 synthetic entities:
- **Meter ID**: `50000000-0000-0000-0000-000000000001` (from [`data/synthetic/meters.json`](../meters.json))
- **Energy Asset ID**: `60000000-0000-0000-0000-000000000001` (from [`data/synthetic/energy_assets.json`](../energy_assets.json))
- **Site ID**: `40000000-0000-0000-0000-000000000001` (from [`data/synthetic/sites.json`](../sites.json))

## Usage

Use the Python loader from `backend/tests/fixtures/telemetry`:

```python
from backend.tests.fixtures.telemetry import load_telemetry_fixture

valid_readings = load_telemetry_fixture("valid")
missing_readings = load_telemetry_fixture("missing")
stale_readings = load_telemetry_fixture("stale")
```
