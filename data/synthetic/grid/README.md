# UrjaSetu Phase 5 Grid Scenarios and Fixtures

Deterministic synthetic distribution grid scenarios representing physical network conditions, thermal loading limits, voltage constraints, and trade validation in UrjaSetu.

---

## Overview

In accordance with [docs/04_DATA_MODEL.md](../../../docs/04_DATA_MODEL.md) (Entities 4, 16, 17) and canonical interfaces in `app.domain.interfaces.grid`:
- **Radial Feeder Topology**: Feeder/Substation root (11 kV) step-down to distribution transformers (0.415 kV / 250 kW) feeding connection points (0.415 kV / 50 kW).
- **Physical Sign Convention**: Injections follow generator convention — **positive is generation into the network, negative is consumption/load**.
- **Deterministic Limits**: Default operating envelope is $\pm 6\%$ voltage ($0.94 - 1.06\text{ pu}$) and $100\%$ thermal loading for lines and transformers.
- **Three-State Verdict**: An engine's finding is `SAFE`, `UNSAFE`, or `UNKNOWN` (missing ratings or solver divergence downgrade to `UNKNOWN`, never guessing `SAFE`).
- **Trade Judgement**: Decides between `ACCEPT` and `REJECT` based on whether the trade itself introduced new violations.

---

## Radial Network Topology & Node Identifiers

| Node ID | External Ref | Type | Nominal Voltage | Parent Node ID | Default Continuous Rating |
|---|---|---|---|---|---|
| `10000000-0000-0000-0000-000000000001` | `DEMO-FEEDER-GJ-001` | `substation` | 11.0 kV | `null` (Root) | N/A (Root bus) |
| `10000000-0000-0000-0000-000000000002` | `DEMO-DTR-GJ-001-A` | `transformer` | 0.415 kV | `...0001` | 250.0 kW (Nameplate) |
| `10000000-0000-0000-0000-000000000003` | `DEMO-DTR-GJ-001-B` | `transformer` | 0.415 kV | `...0001` | 250.0 kW (Nameplate) |
| `10000000-0000-0000-0000-000000000004` | `DEMO-NODE-GJ-001-A-L1` | `connection_point` | 0.415 kV | `...0002` | 50.0 kW (Conductor) |
| `10000000-0000-0000-0000-000000000005` | `DEMO-NODE-GJ-001-A-L2` | `connection_point` | 0.415 kV | `...0002` | 50.0 kW (Conductor) |
| `10000000-0000-0000-0000-000000000006` | `DEMO-NODE-GJ-001-B-L1` | `connection_point` | 0.415 kV | `...0003` | 50.0 kW (Conductor) |

---

## 11 Evaluated Scenarios

| File | Scenario ID | Description | Status | Decision | Primary Constraint / Behavior |
|---|---|---|---|---|---|
| `01_healthy_radial_feeder.json` | `healthy_radial_feeder` | Radial feeder with balanced loads & solar. | `SAFE` | `ACCEPT` | Voltages within 0.99-1.01 pu; loadings < 35%. |
| `02_rated_line_below_current_flow.json` | `rated_line_below_current_flow` | Conductor continuous rating is 30 kW; current flow is 39 kW. | `UNSAFE` | `REJECT` | `LINE_OVERLOAD` (130.0% loading vs 100.0% limit). |
| `03_rated_transformer_below_current_flow.json` | `rated_transformer_below_current_flow` | Transformer rating is 100 kW; aggregate flow is 120 kW. | `UNSAFE` | `REJECT` | `TRANSFORMER_OVERLOAD` (120.0% loading vs 100.0% limit). |
| `04_voltage_violation.json` | `voltage_violation` | High reverse solar injection drives bus voltage to 1.0850 pu. | `UNSAFE` | `REJECT` | `OVER_VOLTAGE` (1.0850 pu vs 1.0600 pu limit). |
| `05_line_overload.json` | `line_overload` | Heavy downstream customer draw pushes line loading to 125%. | `UNSAFE` | `REJECT` | `LINE_OVERLOAD` (125.0% loading vs 100.0% limit). |
| `06_transformer_overload.json` | `transformer_overload` | Downstream feeder demand pushes DTR-A loading to 115%. | `UNSAFE` | `REJECT` | `TRANSFORMER_OVERLOAD` (115.0% loading vs 100.0% limit). |
| `07_multiple_simultaneous_violations.json` | `multiple_simultaneous_violations` | Extreme solar injection causes concurrent multi-element failure. | `UNSAFE` | `REJECT` | `OVER_VOLTAGE` (1.082 pu), `LINE_OVERLOAD` (120%), `TRANSFORMER_OVERLOAD` (114%). |
| `08_unrated_edge_unknown_validation.json` | `unrated_edge_unknown_validation` | Node 5 line has no recorded rating (`rating_kw = null`). | `UNKNOWN` | `REJECT` | Thermal limits unassessable; `resolve_status` downgrades `SAFE` to `UNKNOWN`. |
| `09_solver_failure_unknown.json` | `solver_failure_unknown` | Non-converging power flow simulation. | `UNKNOWN` | `REJECT` | Engine failure records `UNKNOWN`; never passes an unverified network. |
| `10_safe_proposed_trade.json` | `safe_proposed_trade` | Proposed market trade (15 kWh) adds injections within limits. | `SAFE` | `ACCEPT` | Network remains within all voltage and thermal limits; trade accepted. |
| `11_unsafe_proposed_trade.json` | `unsafe_proposed_trade` | Proposed trade adds 45 kW export on a 35 kW conductor. | `UNSAFE` | `REJECT` | Trade causes `LINE_OVERLOAD` (142.8%) not present in baseline; trade rejected. |

---

## Schema Adherence

### `NetworkNode` (Entity 4)
```json
{
  "id": "10000000-0000-0000-0000-000000000004",
  "external_ref": "DEMO-NODE-GJ-001-A-L1",
  "node_type": "connection_point",
  "nominal_voltage_kv": "0.4150",
  "parent_node_id": "10000000-0000-0000-0000-000000000002",
  "feeder_id": "DEMO-FEEDER-GJ-001",
  "rated_capacity_kw": "50.0000"
}
```

### `GridValidationRequest`
```json
{
  "interval_start": "2026-06-02T10:00:00Z",
  "interval_end": "2026-06-02T11:00:00Z",
  "baseline_injections": [
    {"node_id": "10000000-0000-0000-0000-000000000004", "active_power_kw": "4.5000"}
  ],
  "proposed_injections": []
}
```
