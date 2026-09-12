# 07 — Coding Phases and Four-Person Work Plan

> **Workflow lock:** Every phase ends with a test/integration gate. The team does not begin the next phase until Yagnik verifies the current phase.

> **Phase sequence lock (2026-09-12):** the canonical numbering is the ten phases
> listed below. It differs from an earlier draft of this document, which placed
> pricing at Phase 5 and the grid twin at Phase 6, and which numbered up to 12.
> Where a brief, a commit message or a code comment names a phase, this table is
> what it means.
>
> | Phase | Scope |
> |-------|-------|
> | 0 | Foundation |
> | 1 | Identity + Asset Registry |
> | 2 | Telemetry |
> | 3 | Forecasting |
> | 4 | Marketplace + Matching |
> | 5 | Grid Validation |
> | 6 | Dynamic Pricing |
> | 7 | Settlement + Reconciliation |
> | 8 | Audit / DLT |
> | 9 | Frontend / Dashboard |
>
> Alembic revision identifiers are **not** renumbered to match. `0006_grid_validation`
> is the sixth migration, not "Phase 6" — migrations are numbered by order of
> application and never renamed once written.

## Global Phase Rules

1. `main` is protected.
2. Every agent creates a phase-specific branch from the latest verified `main`.
3. Agents never commit, push, merge, rebase, force-push, or modify `main` themselves.
4. Agents make changes only inside their owned paths for that phase.
5. Before returning work, each agent runs the phase's required tests.
6. Yagnik reviews the diff, runs integration tests, resolves conflicts if any, and performs the final commit/merge.
7. Never rewrite a previous migration after it has been merged.
8. Never change locked API/schema contracts without Yagnik approval.

## Phase 0 — Foundation / Backend + DB Connectivity

### Yagnik — PRIMARY OWNER
Do all core setup:
- repository scaffold
- Python environment
- FastAPI app
- PostgreSQL Docker service
- SQLAlchemy engine/session
- Pydantic settings
- Alembic
- base model conventions
- health/readiness endpoints
- API version router
- error envelope
- project scripts
- baseline CI
- developer docs

Must also create the first minimal migration proving:
`FastAPI -> SQLAlchemy -> PostgreSQL -> Alembic`

Must NOT start market/grid/forecast implementation.

### Manthan
Read-only initially. May prepare a written review of setup risks in `docs/reviews/phase-0.md` only.
Do not modify backend architecture.

### Siddhant
Add only smoke/integration test cases under `backend/tests/integration/phase0/` after Yagnik exposes stable app/db fixtures.
Do not touch DB models or migrations.

### Vedant
Add only developer setup verification notes/checklist under `docs/reviews/phase-0.md` after Yagnik setup is visible. Do not change runtime files.

### Gate
- app starts
- DB connects
- migration runs from empty DB
- health and readiness pass
- one ORM read/write test passes
- clean startup from Docker Compose

---

## Phase 1 — Identity, Sites, Assets, Meters, Verification

### Yagnik
Own:
- users
- sites
- meters
- energy assets
- inverter metadata
- verification
- consent models
- repositories/services/contracts

### Manthan
Own API tests for assets/verification under assigned test directory.
Do not edit models or migrations.

### Siddhant
Own seed fixtures for a small community dataset under `data/synthetic/` and seed script additions only.

### Vedant
Own validation/edge-case test cases for verification eligibility logic under tests only.

### Gate
End-to-end:
`create user -> create site -> attach meter -> add PV -> verify -> eligibility`

---

## Phase 2 — Telemetry Ingestion + Data Quality

### Yagnik
Own normalized telemetry schema and service interface.

### Manthan
Own batch CSV/synthetic importer under `scripts/` and `app/adapters/meter/simulator_adapter.py`.

### Siddhant
Own telemetry API tests and validation edge cases.

### Vedant
Own data-quality fixtures: missing/stale/out-of-order readings.

### Gate
Ingest -> store -> query latest -> query interval -> quality status.

---

## Phase 3 — Forecasting Interface + Baseline Model

### Yagnik
Own `ForecastProvider` interface, domain contracts and service orchestration.

### Manthan
Implement one baseline forecast provider only in `app/adapters/forecast/`.

### Siddhant
Evaluate forecast output shape and write provider contract tests.

### Vedant
Prepare representative forecast datasets/fixtures and basic accuracy metrics test harness.

Nobody may hard-code the selected forecasting algorithm into market code.

### Gate
Telemetry -> forecast provider -> forecast_points -> surplus endpoint.

---

## Phase 4 — Market Sessions, Orders, Matching

### Yagnik
Own order/trade DB schema, state machine and service orchestration.

### Manthan
Own matching algorithm module under `domain/policies/market_matching.py`.

### Siddhant
Own order validation and matching test suite.

### Vedant
Own deterministic market scenario fixtures.

### Gate
Orders -> order book -> matching -> proposed trades with deterministic expected outputs.

---

## Phase 5 — Grid Validation + Distribution Network

### Yagnik
Own UrjaSetu grid abstractions, validation service and adapter boundary.

### Manthan
Implement Power Grid Model adapter only.

### Siddhant
Own grid-validation tests and known safe/unsafe fixtures.

### Vedant
Create feeder/transformer/network scenarios and demo data.

### Gate
Proposed trade -> power flow -> normalized result -> safe / unsafe / unknown decision.
A solver failure or a gap in the twin is recorded as `unknown` and never as safe.

---

## Phase 6 — Dynamic Pricing

Pricing and the grid-aware market feedback it depends on. These were separate
phases in the earlier draft; they are one phase because choosing a remedy for an
unsafe trade — reprice, reduce, shift — *is* a pricing decision, and it consumes
the violations Phase 5 records.

### Yagnik
Own pricing interface/formula versioning and persistence contract, and the
combined grid-and-market decision workflow.

### Manthan
Implement pricing policy module only, including the reprice/reduce/shift policy
as an isolated policy module.

### Siddhant
Test formula boundaries and rounding, and own end-to-end congestion scenarios.

### Vedant
Create benchmark scenarios: low/high supply, peak/off-peak, congestion levels,
and scenario runner scripts for demo stress cases.

### Gate
Same input + same formula version = same price breakdown. An unsafe trade cannot
become approved without a valid safe / repriced / reduced path.

---

## Phase 7 — Settlement + Reconciliation

### Yagnik
Own settlement transaction model and state machine.

### Manthan
Implement reconciliation calculations.

### Siddhant
Test tolerance, deficit, surplus, balancing and rounding.

### Vedant
Create settlement scenario fixtures and expected reports.

### Gate
Committed -> actual -> deviation -> final settlement is reproducible and auditable.

---

## Phase 8 — Audit / DLT

### Yagnik
Own audit domain and adapter interface.

### Manthan
Implement append-only hash-chain audit in PostgreSQL first.

### Siddhant
Test audit integrity and replay.

### Vedant
Research/prototype Fabric adapter only after Yagnik authorizes this phase.

### Gate
All material trade/settlement events produce verifiable audit records.

---

## Phase 9 — Frontend / Dashboard

Frontend begins only after the backend integration gate passes. Realtime event
delivery is part of this phase: it exists to serve the dashboard, and REST
remains authoritative regardless.

### Yagnik
Own the event contract, WebSocket gateway integration, API client conventions
and final integration.

### Manthan
Implement the market event publisher integration and the marketplace UI.

### Siddhant
Test reconnect/state-refetch semantics; build the grid dashboard.

### Vedant
Implement grid/telemetry event adapters as assigned; build the
community/prosumer dashboard.

All frontend agents consume the existing API contracts; they do not modify
backend schema ad hoc.

### Gate
REST remains authoritative; WebSocket updates are timely and reconnect-safe.

---

## Demo hardening (continuous, not a numbered phase)

Runs alongside the later phases rather than after them. All four members may
work here, but each must own separate files/modules.

Required scenarios:
- solar noon surplus
- demand spike
- feeder congestion
- forecast under-delivery
- stale telemetry
- failed adapter
- 100 -> 1,000 -> 10,000 synthetic entities
