# 06 — Open-Source Integration Plan

## Golden Rule

**Reuse mature capability; build our domain integration and policies.** Do not clone a project wholesale.

## 1. Power Grid Model — CORE GRID INTEGRATION

Repository:
`https://github.com/PowerGridModel/power-grid-model`

Use for:
- power flow
- state estimation where useful
- short-circuit analysis if a later demo needs it

Integration boundary:
`app/adapters/grid/power_grid_model_adapter.py`

Input adapter converts UrjaSetu digital-twin state to Power Grid Model input.
Output adapter converts results to our normalized:
- min/max voltage
- max line loading
- transformer loading
- safe/unsafe
- diagnostic reasons

Do not spread Power Grid Model classes across market services.

## 2. pySunSpec2 — DEVICE INTEROPERABILITY

Repository:
`https://github.com/sunspec/pysunspec2`

Use for:
- future SunSpec Modbus RTU/TCP ingestion
- inverter telemetry adapter examples

Integration boundary:
`app/adapters/inverter/sunspec_adapter.py`

For MVP, the adapter can remain a stub/mock with recorded data. Do not require physical inverter hardware.

## 3. InterConnect P2P Marketplace — MARKET REFERENCE

Repository supplied by team:
`https://gitlab.inesctec.pt/interconnect-public/p2p-marketplace/-/tree/p2p-energy-trading`

Use for architectural study:
- order matching concepts
- aggregation
- marketplace lifecycle
- smart-contract boundaries

Do not copy its entire application into UrjaSetu.

We implement UrjaSetu's own domain models and grid-aware decision loop.

## 4. Grid Singularity GSY-E — MARKET SIMULATION REFERENCE

Repository:
`https://github.com/gridsingularity/gsy-e`

Use for:
- market simulation concepts
- scenario generation
- understanding local energy-market mechanics

Do not make it a hard dependency in the MVP unless an actual integration test proves it helps. Its repository is GPL-3.0; licensing must be reviewed before embedding/distributing code.

## 5. OpenSTEF — FORECASTING REFERENCE / OPTIONAL ADAPTER

Repository:
`https://github.com/OpenSTEF/openstef`

Use for:
- short-term forecast architecture
- feature engineering ideas
- probabilistic forecasting concepts

Initial UrjaSetu forecasting interface must allow:
- baseline model
- XGBoost/LightGBM
- OpenSTEF-backed provider
without changing market code.

## 6. Hyperledger Fabric — OPTIONAL AUDIT LAYER

Repository:
`https://github.com/hyperledger/fabric`

Use later for:
- permissioned audit proofs
- finalized trade/settlement hashes
- smart-contract-controlled audit records if required

Operational market data stays in PostgreSQL.

## 7. Hyperledger FireFly — OPTIONAL ORCHESTRATION

Repository:
`https://github.com/hyperledger-firefly/firefly`

Do not introduce in Phase 0.

Evaluate only after a Fabric proof-of-concept exists and an orchestration problem is identified. It is not necessary merely because Fabric exists.

## 8. Energy Web — ARCHITECTURE REFERENCE

Repository supplied by team:
`https://github.com/energywebfoundation/paper`

Use as research/reference for energy-specific DLT and interoperability patterns. Not an MVP dependency.

## Integration Decision Table

| Capability | Source | MVP action |
|---|---|---|
| Grid power flow | Power Grid Model | Integrate |
| Inverter protocol | pySunSpec2 | Adapter/stub now; real adapter later |
| Marketplace ideas | InterConnect | Study/adapt |
| Energy-market simulation | GSY-E | Study; optional later |
| Forecasting | OpenSTEF | Provider candidate; not hard dependency |
| DLT | Fabric | Optional later |
| DLT orchestration | FireFly | Defer |
| Energy blockchain ideas | Energy Web | Reference only |
