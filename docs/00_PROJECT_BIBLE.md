# 00 — Project Bible

> **Status: LOCKED**
>
> Changes require Yagnik's explicit approval and a documented architecture decision.

## 1. One-Sentence Definition

**UrjaSetu is a grid-aware local renewable-energy marketplace that predicts supply/demand, matches renewable energy orders, validates proposed trades against distribution-grid constraints, dynamically prices/limits trades, reconciles actual meter data and performs auditable settlement.**

## 2. Non-Negotiable Interpretation

We do **not** model or claim physical peer-to-peer electron routing.

Physical layer:
- existing distribution grid
- DISCOM / authorized utility infrastructure
- meters and approved generation interconnection

Digital layer:
- identity and asset verification
- energy telemetry
- forecasting
- orders and matching
- grid validation
- price calculation
- trade commitments
- reconciliation
- settlement
- auditability

## 3. MVP Boundary

The MVP represents a local community / simulated feeder. Production deployment would require the relevant DISCOM, regulator and authorized market integration.

Hackathon data can combine:
- Indian smart-meter/load datasets
- public PV-generation datasets
- weather/irradiance data
- synthetic prosumer profiles calibrated to Indian conditions

## 4. Core Loop

```text
DATA
  -> FORECAST
  -> MARKET
  -> GRID VALIDATION
  -> ACCEPT / REPRICE / REDUCE / SHIFT / REJECT
  -> TRADE COMMITMENT
  -> ACTUAL METER RECONCILIATION
  -> SETTLEMENT
  -> AUDIT
```

The grid-validation result feeds back into the market. This feedback loop is the core differentiator.

## 5. Design Principles

### Reliability
A stale or missing data source must not crash the marketplace.

### Modularity
Forecast algorithms, pricing formulas, grid engines, AI providers and device integrations are replaceable adapters.

### Traceability
Every material business decision must be explainable from stored inputs and outputs.

### Deterministic safety
Grid safety is determined by a deterministic grid-analysis layer, not an AI model.

### Minimal complexity
Do not add Kafka, Fabric, FireFly, Kubernetes or other infrastructure unless a phase explicitly needs it.

### API-first backend
All business logic lives in backend services/domain modules, not frontend code.

### Database as source of operational truth
PostgreSQL is the operational source of truth. DLT is optional audit infrastructure, never the primary application database.

## 6. Units and Conventions

- Power: kW
- Energy: kWh
- Price: INR/kWh
- Currency: INR / paise internally where needed
- Voltage: per-unit (pu)
- Time: UTC in storage/API timestamps; localized only at UI boundary
- Intervals: explicit `interval_start` and `interval_end`
- IDs: UUIDs

## 7. Market Model

The first market mode is **day-ahead commitment** because current Indian P2P pilot material describes tomorrow's trades and DISCOM verification. Real-time/intra-day telemetry is still used for forecast updates, grid-state evaluation and pre-execution/re-pricing logic in the prototype; the system must not present this as authorized same-day residential retail trading.

## 8. Security / Privacy Baseline

Never expose:
- raw secrets
- passwords
- private keys
- API tokens
- full personal identifiers in public dashboards

Use opaque internal IDs and role-based authorization. Real utility/customer data must be anonymized before ingestion into development datasets.

## 9. What We Will Build vs Reuse

Build ourselves:
- Indian community/prosumer model
- domain schemas
- market workflow
- matching policy
- grid-aware decision loop
- congestion-aware price composition
- reliability/reconciliation logic
- settlement rules
- backend API/domain integration

Reuse/adapt:
- Power Grid Model for distribution analysis
- pySunSpec2/SunSpec concepts for device interoperability
- InterConnect as marketplace architecture reference
- Grid Singularity as market-simulation reference
- OpenSTEF as forecasting reference when needed
- Hyperledger Fabric only for optional audit/DLT phase

## 10. Forbidden Shortcuts

Do not:
- put all sensor telemetry on blockchain
- write a custom power-flow solver
- hard-code a single inverter vendor
- let an LLM approve/reject grid trades
- store money or settlement totals only in frontend state
- make frontend call PostgreSQL directly
- create a second incompatible schema in a feature branch
- silently change locked architecture
