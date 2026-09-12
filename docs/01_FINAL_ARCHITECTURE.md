# 01 — Final Architecture

## Logical Layers

1. User / Actor Registry
2. Asset & Verification Registry
3. Data Ingestion / Normalization
4. Community Digital Twin
5. Forecasting Engine
6. Market Engine
7. Grid Validation Engine
8. Dynamic Pricing Engine
9. Trade Commitment & Reconciliation
10. Settlement Engine
11. Audit / DLT Adapter
12. API / Realtime Delivery
13. Frontend dashboards (later)

## Runtime Architecture

```text
Clients
  |
  v
API / WebSocket Gateway
  |
  +--> Identity / Users
  +--> Assets / Verification
  +--> Telemetry ingestion
  +--> Forecast service
  +--> Market service
  +--> Grid service
  +--> Settlement service
  +--> Audit service
  |
  v
PostgreSQL
  |
  +--> operational relational data
  +--> time-series telemetry
  +--> market state
  +--> settlement records

External / replaceable adapters
  +--> Weather API
  +--> SunSpec / vendor inverter APIs
  +--> Smart meter / AMI source
  +--> Power Grid Model
  +--> Forecast model provider
  +--> Optional Hyperledger Fabric
```

## Data Flow

```text
Meter / Inverter / Simulator
        |
        v
Normalization
        |
        v
Telemetry Store -----> Forecasting
        |                   |
        |                   v
        |              Forecast + confidence
        |                   |
        +-------------------+
                            v
                    Market Order Book
                            |
                            v
                       Matching
                            |
                            v
                    Proposed Trade Set
                            |
                            v
                     Grid Power Flow
                       /          \
                    safe          unsafe
                     |              |
                     v              v
                 execute       reprice / reduce
                     |         / shift / reject
                     +------------->
                            |
                            v
                    Actual reconciliation
                            |
                            v
                        Settlement
                            |
                            v
                         Audit
```

## Services / Modules

The codebase is a modular monolith for the MVP. Modules have clear boundaries but run in one backend deployment.

### `identity`
Users, roles, consent.

### `assets`
Sites, meters, PV assets, inverters, grid nodes, verification.

### `telemetry`
Ingestion, validation, quality flags, normalized readings.

### `forecasting`
Forecast provider interface, forecast runs, confidence.

### `market`
Market sessions, bids/offers, matching, proposed trades.

### `grid`
Grid model adapter, power-flow runs, constraints, validation decisions.

### `pricing`
Base price + time + congestion + imbalance/risk + local-renewable component.

### `settlement`
Actual-versus-committed reconciliation, adjustments, buyer/seller accounting.

### `audit`
Business event trail and optional DLT anchoring.

## Reliability Paths

### Stale telemetry
`live -> last-known-valid -> forecast -> confidence reduction -> trading limit`

### Forecast under-delivery
`commitment -> actual -> deviation -> tolerance -> balancing adjustment`

### Grid congestion
`proposed trade -> power flow -> constraint violation -> reprice/reduce/shift/reject`

### Adapter failure
External integration failures must be isolated from domain services and return typed, observable errors.
