<p align="center">
  <h1 align="center">⚡ UrjaSetu</h1>
  <p align="center"><strong>Grid-Aware Local Renewable Energy Marketplace</strong></p>
  <p align="center">
    Forecast-driven energy trading · Power-flow validated · Dynamically priced · Settled · Blockchain-anchored
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19" />
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL 18" />
  <img src="https://img.shields.io/badge/Solidity-^0.8.20-363636?logo=solidity&logoColor=white" alt="Solidity" />
  <img src="https://img.shields.io/badge/Power_Grid_Model-1.13-orange" alt="Power Grid Model" />
  <img src="https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=githubactions&logoColor=white" alt="CI" />
</p>

---

> **Energy trading is easy to imagine. Making every trade forecast-aware, grid-feasible, dynamically priced, metered, settled, and independently verifiable on a blockchain is the engineering challenge UrjaSetu addresses.**

UrjaSetu connects distributed renewable-energy producers (rooftop solar households) with nearby energy demand through an eight-phase pipeline: telemetry ingestion → generation forecasting → surplus calculation → marketplace matching → distribution-network power-flow validation → dynamic pricing → metered settlement → blockchain-anchored audit trail. A React dashboard lets households see their live power, place orders, watch trades clear, and verify settlement receipts against a real Ethereum-compatible ledger.

**Energy and INR accounting are simulated.** Weather data comes from Open-Meteo. No physical meter, inverter, bank account, or DISCOM system is connected. The fictional Gujarat community, feeder topology, and pricing parameters are demonstration assumptions — not approved tariffs or an authorized electricity trading service.

---

## Quick Facts

| Category | UrjaSetu |
|---|---|
| **Domain** | Distributed Renewable Energy / Local P2P Marketplace |
| **Architecture** | Modular monolith — domain-driven layers with adapter boundaries |
| **Backend** | Python 3.12 · FastAPI · SQLAlchemy 2.0 · Pydantic 2.9 · Alembic |
| **Frontend** | React 19 · TypeScript 5.9 · Vite 7 · Recharts · React Flow · Motion |
| **Database** | PostgreSQL 18 — 25+ tables, native enums, JSONB audit payloads |
| **Grid Simulation** | Power Grid Model 1.13 — Newton-Raphson symmetric power flow |
| **Forecasting** | Pluggable provider interface · baseline solar/load provider |
| **Pricing** | 5-component dynamic formula: base + time + congestion + imbalance + local-renewable |
| **Settlement** | Meter reconciliation → tolerance policy → double-entry accounting |
| **Audit** | SHA-256 chained events · canonical serialization · chain verification |
| **Blockchain** | Solidity `ReceiptRegistry` on local EVM · Python JSON-RPC publisher |
| **Real-time** | WebSocket gateway with typed event bus |
| **AI Assistant** | Account-aware energy guide with optional Gemini integration |
| **CI** | GitHub Actions — lint, typecheck, migrate, test against live PostgreSQL |
| **Testing** | pytest (unit/integration/API) · Vitest · Playwright E2E browser tests |

---

## Why UrjaSetu?

Rooftop solar turns millions of electricity consumers into producers. But electricity is not a file you can share — it flows through a physical distribution network governed by voltage limits, thermal ratings, and time-of-day demand patterns.

**The problem is not trading. The problem is trading *safely, fairly, and provably*.**

| Challenge | Why it matters |
|---|---|
| **Generation varies** | Solar output changes with weather, cloud cover, and time of day |
| **Demand varies independently** | A household's load profile does not follow solar irradiance |
| **The grid has physical limits** | Injecting power where conductors are loaded or voltage is marginal causes harm |
| **Price should reflect reality** | A trade during feeder congestion costs the network more than one during slack |
| **Settlement must be honest** | What was forecast, what was committed, and what was actually delivered are three different numbers |
| **Trust requires evidence** | Every decision — matching, validation, pricing, settlement — should be independently verifiable |

UrjaSetu does not simply match a buyer and a seller. It builds an end-to-end pipeline where **every trade is forecast-backed, grid-validated, dynamically priced, metered, settled with deviation accounting, audited in a tamper-evident chain, and optionally anchored to a blockchain**.

---

## How UrjaSetu Works — Eight Phases

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                        UrjaSetu Pipeline                           │
 │                                                                     │
 │  ① Ingest  →  ② Forecast  →  ③ Surplus  →  ④ Match  →  ⑤ Grid     │
 │     ↓            ↓              ↓             ↓           ↓        │
 │  telemetry    solar/load    exportable     order book   power flow  │
 │  readings     predictions   energy calc    clearing     validation  │
 │                                                                     │
 │  ⑥ Price  →  ⑦ Settle  →  ⑧ Audit                                 │
 │     ↓            ↓            ↓                                     │
 │  5-component  reconcile +   chain seal +                            │
 │  formula      accounting    ledger anchor                           │
 └─────────────────────────────────────────────────────────────────────┘
```

### 01 — Ingest (`telemetry_service`)
Collect meter readings (generation kW, load kW, energy kWh) per 15-minute interval. Each reading is quality-classified — valid, stale, duplicate, or missing — and never silently dropped. Adapters exist for CSV import, real-time simulation, and a profile-driven household simulator.

### 02 — Forecast (`forecast_service` · `BaselineForecastProvider`)
Estimate solar generation and household load over a future horizon. The forecast service gathers 14 days of historical telemetry, passes it to a pluggable `ForecastProvider`, validates the result at the boundary, and persists forecast points with confidence intervals. The baseline provider uses sinusoidal solar curves shaped by site capacity and Open-Meteo cloud-cover data.

### 03 — Surplus (`surplus` policy)
Compare the newest solar forecast with the newest load forecast for a site. The difference — generation minus self-consumption — is the **exportable energy**: what a seller may offer to the market. A sell order that exceeds available surplus is rejected at order placement, not discovered at delivery.

### 04 — Match (`market_service` · `MatchingEngine`)
Day-ahead market sessions open, accept buy and sell orders, close, and clear. The matching engine receives an immutable `OrderBook` snapshot, produces proposed trades with a clearing price, and returns them. The service validates engine output at the boundary — no over-fill, no wrong-side pairing, no phantom orders — before writing trades as `proposed`. An audit event is chained for every order placed, market cleared, and trade proposed.

### 05 — Grid Validate (`grid_validation_service` · `PowerGridModelAdapter`)
Every proposed trade is checked against the physical distribution network using **Power Grid Model** (Newton-Raphson symmetric three-phase power flow). The seller injects and the buyer withdraws the same power, simulating the actual transfer. The result reports voltage (per-unit), line loading (%), and transformer loading (%). A limits policy decides: **accept**, **flag**, or **reject**. Unrated network elements downgrade `SAFE` to `UNKNOWN` — honesty over false confidence.

### 06 — Price (`pricing_service` · `dynamic_pricing` policy)
Five transparent components:

| Component | Source | Sign |
|---|---|---|
| **Base market price** | Phase 4 clearing price | baseline |
| **Time-of-day** | IST tariff band (peak / shoulder / off-peak / solar) | ± |
| **Congestion** | Phase 5 grid loading metrics | ≥ 0 |
| **Imbalance** | Phase 3 forecast confidence | ≥ 0 |
| **Local renewable** | Same-feeder trade with active PV asset | ≤ 0 (incentive) |

Each component is a fraction of the base price, so the formula is currency-agnostic. The final price is validated: components must sum to the total, congestion and imbalance must never be negative, the local-renewable incentive must never be positive. The `formula_version` is stored with every breakdown so a price computed today stays explainable under a future formula revision.

### 07 — Settle (`settlement_service`)
Reconciliation compares actual metered energy with the committed quantity: within tolerance → settled at committed; deviation → balancing charge. Settlement produces gross amount, platform fee, balancing charge, buyer debit, and seller credit — and verifies that **the two sides balance**. A calculator that returns a ledger that doesn't balance is rejected before any money is recorded.

### 08 — Audit (`audit_service` · `audit_chain` policy)
Every domain action — order, clearing, trade, grid validation, pricing, reconciliation, settlement — is recorded as a **chained, hash-linked audit event**. The chain is global (not per-entity), so removing *any* event anywhere breaks verification. Events are canonically serialized (deterministic key order, no floats, UTC-normalised timestamps, Decimal as plain strings) and hashed with SHA-256. Optionally, individual events are **anchored to a Solidity `ReceiptRegistry`** on a local EVM blockchain.

---

## Key Features

### ⚡ Energy Intelligence
- **Solar & load forecasting** with pluggable provider architecture and confidence intervals
- **Surplus calculation** pairing generation and consumption forecasts per site
- **Telemetry quality classification** — valid, stale, duplicate, missing — never silent drops
- **Profile-driven household simulation** using Open-Meteo weather context
- **Forecast evaluation** tooling for accuracy analysis

### 🏪 Local Energy Marketplace
- **Day-ahead market sessions** with open → close → clear lifecycle
- **Order book construction** with buy/sell sides, limit prices, delivery windows
- **Pluggable matching engine** with boundary-validated output
- **Eligibility enforcement** — seller must have forecast surplus, buyer must be verified
- **Real-time WebSocket notifications** for orders, trades, clearing, and settlement

### 🔌 Grid-Aware Validation
- **Newton-Raphson power flow** via Power Grid Model (LF distribution networks)
- **Digital twin** of feeder topology: nodes, lines, transformers with rated capacities
- **Per-trade feasibility** — seller injects, buyer withdraws, network effects evaluated
- **Voltage and thermal limit policies** with configurable thresholds
- **Input fingerprinting** — SHA-256 hash of every validation's exact inputs for reproducibility
- **Unrated-element honesty** — unknown ratings produce `UNKNOWN`, never false `SAFE`

### 💰 Dynamic Pricing & Settlement
- **5-component transparent pricing** with stored formula versioning
- **Meter reconciliation** comparing actual delivery vs. commitment
- **Deviation tolerance** with configurable policy
- **Double-entry settlement accounting** — buyer debit ≡ seller credit + platform retained
- **Settlement superseding** — corrections append, never overwrite

### 🔐 Trust & Audit
- **Append-only hash chain** — SHA-256 linked, global scope
- **Canonical serialization** — deterministic JSON with sorted keys, no floats, UTC timestamps
- **Chain verification** — recomputes every hash from stored content, detects any tampering
- **Blockchain anchoring** — Solidity `ReceiptRegistry` on local EVM, verified via JSON-RPC
- **Ledger anchor boundary** — the chain is authoritative in PostgreSQL; blockchain is evidence

### 📊 Connected Dashboard
- **Live power monitoring** with 5-second auto-refresh and configurable intervals
- **Energy charts** — generation, consumption, and net energy over time (Recharts)
- **Marketplace UI** — place orders, browse offers, execute trades with real-time updates
- **Grid monitor** — feeder topology visualization with React Flow
- **Settlements & statements** — credits, debits, savings with CSV export
- **Blockchain receipt verification** — verify settlement hashes against the running EVM
- **Community view** — household cards, photos, capacity, sharing preferences
- **AI energy assistant** — answers account/forecast questions with optional Gemini backend

---

## System Architecture

```mermaid
flowchart TB
    subgraph Frontend["Frontend — React 19 + TypeScript"]
        UI[Dashboard & Marketplace]
        WS_C[WebSocket Client]
    end

    subgraph API["API Layer — FastAPI"]
        REST[REST API v1]
        WS_S[WebSocket Gateway]
        AUTH[Auth & Session]
    end

    subgraph Services["Service Layer"]
        TEL[Telemetry Service]
        FCS[Forecast Service]
        MKT[Market Service]
        GRD[Grid Validation Service]
        PRC[Pricing Service]
        STL[Settlement Service]
        AUD[Audit Service]
        WRK[Workspace Service]
        EXP[Experience Service]
    end

    subgraph Domain["Domain Layer"]
        POL[Policies — surplus, pricing,<br/>grid limits, settlement,<br/>audit chain, matching,<br/>eligibility, telemetry quality]
        INT[Interfaces — typed contracts<br/>for engines, providers,<br/>publishers, resolvers]
        ENM[Enumerations — 35+ domain<br/>types as PostgreSQL enums]
    end

    subgraph Adapters["Adapter Layer"]
        PGM[Power Grid Model<br/>Newton-Raphson solver]
        BFP[Baseline Forecast<br/>Provider]
        CSV[CSV / Simulator<br/>Meter Adapters]
        EVM[EVM Publisher<br/>JSON-RPC]
    end

    subgraph Data["Persistence"]
        PG[(PostgreSQL 18<br/>25+ tables)]
        BC[Local EVM<br/>ReceiptRegistry]
    end

    UI --> REST
    UI <--> WS_C
    WS_C <--> WS_S
    REST --> AUTH
    AUTH --> Services
    WS_S --> Services
    Services --> Domain
    Services --> Adapters
    GRD --> PGM
    FCS --> BFP
    TEL --> CSV
    AUD --> EVM
    Services --> PG
    EVM --> BC
```

### Separation principle

The architecture enforces strict boundaries:
- **Services** own transaction boundaries and orchestration — they contain no algorithms
- **Policies** contain the actual rules — pure, deterministic, independently testable
- **Adapters** wrap external dependencies — Power Grid Model, EVM, forecast providers
- **Interfaces** define typed contracts between layers — engines, providers, and resolvers are Protocols

A service never imports a concrete adapter. A policy never touches the database. An adapter never decides business rules. This is how modules stay independently replaceable.

---

## Trust & Audit Architecture

This is the system's integrity backbone. The audit layer records what happened, and the blockchain proves the record wasn't altered.

```
 Application Event (order, trade, settlement, ...)
            │
            ▼
 Canonical Serialization
   • sorted keys, recursively
   • Decimal → plain string (never float)
   • datetime → UTC ISO microseconds
   • UUID → string form
   • no incidental whitespace
            │
            ▼
 SHA-256 Hash (covers event + predecessor link)
            │
            ▼
 Chained Audit Event
   • event_hash links to next
   • previous_hash links to predecessor
   • global chain (not per-entity)
            │
            ▼
 PostgreSQL (authoritative record)
            │
            ▼ (optional, outside transaction)
 Ledger Anchor
   • ReceiptRegistry.record(key, digest)
   • local EVM via JSON-RPC
   • idempotent, crash-recoverable
            │
            ▼
 Independent Verification
   • recompute hash from stored content
   • compare on-chain digest with database
   • detect any edit, deletion, or reorder
```

**Key design decisions:**
- **The chain is global**, not per-entity. Deleting an entire entity's history would be undetectable in a per-entity chain.
- **Ledger anchoring is outside the transaction.** A publisher outage cannot stop a trade from settling — the authoritative record already exists in PostgreSQL.
- **Anchoring an event twice is refused**, not silently re-published, so one event cannot accumulate competing references.
- **Floats are forbidden** in audit payloads. `Decimal` is rendered as a plain string so the hashed value is exactly the value the platform used.
- The `ledger_anchor_id` is **excluded from the hash** by design — anchoring happens after recording, and a hash that changed upon publication would invalidate the chain it exists to attest.

**UrjaSetu does not claim to be "blockchain-powered."** The blockchain is an integrity-anchoring layer. The application is PostgreSQL-powered. This distinction is deliberate.

---

## Data Flow

```
 Meter / Simulator / CSV
         │
         ▼
 Telemetry Service
   quality classification (valid / stale / duplicate / missing)
         │
         ▼
 PostgreSQL: telemetry_readings
         │
         ▼
 Forecast Service
   14-day history → ForecastProvider → validated points
         │
         ▼
 Surplus Calculation
   solar forecast − load forecast = exportable energy
         │
         ▼
 Market Service
   order book → matching engine → proposed trades
         │
         ▼
 Grid Validation Service
   network model + injections → Power Grid Model → voltage/loading
         │
         ▼
 Pricing Service
   base + time + congestion + imbalance + local_renewable
         │
         ▼
 Settlement Service
   actual energy vs committed → reconciliation → accounting
         │
         ▼
 Audit Service
   canonical serialize → SHA-256 chain → optional blockchain anchor
         │
         ▼
 Dashboard
   live power · charts · marketplace · grid monitor · receipts
```

---

## Energy Marketplace Lifecycle

```
 Producer (e.g. Asha — 6 kW rooftop solar)
     │
     ▼
 Forecast says: site will produce 3.2 kWh, consume 1.1 kWh → surplus 2.1 kWh
     │
     ▼
 Asha places SELL order: 0.5 kWh, min ₹4/kWh, tomorrow 12:00–12:15 IST
   └── eligibility check: identity verified, active PV asset ✓
   └── surplus check: 2.1 kWh available > 0.5 kWh requested ✓
   └── audit: ORDER_PLACED chained
     │
     ▼
 Consumer (e.g. Ravi) places BUY order: 0.5 kWh, max ₹8/kWh, same slot
     │
     ▼
 Market session closes → matching engine clears
   └── clearing price: ₹6/kWh (midpoint)
   └── boundary validation: no over-fill, correct sides
   └── audit: MARKET_CLEARED + TRADE_PROPOSED chained
     │
     ▼
 Grid validation runs Newton-Raphson power flow
   └── Asha's node injects, Ravi's node withdraws
   └── voltage: 0.97–1.02 pu ✓  |  line loading: 42% ✓
   └── decision: ACCEPT
   └── audit: GRID_VALIDATION_RECORDED chained
     │
     ▼
 Dynamic pricing calculates effective price
   └── base ₹6.00 + time −₹0.30 (solar hours) + congestion ₹0.00
       + imbalance ₹0.12 + local renewable −₹0.60 = ₹5.22/kWh
   └── audit: PRICE_CALCULATED chained
     │
     ▼
 Delivery interval passes → telemetry shows 0.48 kWh actual
     │
     ▼
 Reconciliation: committed 0.50 kWh, actual 0.48 kWh, deviation 0.02 kWh
   └── within 10% tolerance → settled at committed quantity
   └── audit: TRADE_RECONCILED chained
     │
     ▼
 Settlement: gross ₹2.61, platform fee ₹0.13, buyer debit ₹2.61, seller credit ₹2.48
   └── ledger balances ✓
   └── audit: TRADE_SETTLED chained
     │
     ▼
 Blockchain anchor: receipt hash published to ReceiptRegistry on local EVM
   └── independently verifiable: on-chain digest == SHA-256(receipt payload)
```

---

## Technology Stack

### Backend
| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.12 | Strict typing with `disallow_untyped_defs`, modern syntax |
| **FastAPI** | 0.115 | Async API framework with auto-generated OpenAPI docs |
| **SQLAlchemy** | 2.0 | ORM with explicit session management and mapped types |
| **Pydantic** | 2.9 | Request/response validation and settings management |
| **Alembic** | 1.14 | Database migration with autogeneration |
| **uvicorn** | 0.34 | ASGI server with auto-reload for development |
| **psycopg** | 3.2 | PostgreSQL adapter (binary, async-capable) |
| **httpx** | 0.28 | HTTP client for EVM JSON-RPC and Open-Meteo API |

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| **React** | 19 | UI framework with hooks and strict mode |
| **TypeScript** | 5.9 | Type safety across the entire frontend |
| **Vite** | 7.1 | Build tooling with HMR |
| **React Router** | 7.9 | Client-side routing |
| **TanStack Query** | 5.90 | Server state management with stale-while-revalidate |
| **Recharts** | 3.3 | Energy and settlement charts |
| **React Flow** | 12.8 | Grid topology / feeder visualization |
| **Motion** | 12.23 | UI animations and transitions |
| **Lucide React** | 0.468 | Icon system |

### Grid Simulation
| Technology | Version | Purpose |
|---|---|---|
| **Power Grid Model** | 1.13.162 | Newton-Raphson symmetric three-phase power flow solver. Exact-pinned: a solver patch can change a validation result, and past grid decisions must stay reproducible. |

### Blockchain / DLT
| Technology | Purpose |
|---|---|
| **Solidity** ^0.8.20 | `ReceiptRegistry` smart contract — platform-attested receipts. No currency, identities, or meter readings on-chain. |
| **Ganache** | Local EVM development chain (chain ID 1337, deterministic wallets, persistent state) |
| **ethers.js** | Contract deployment and ABI interaction |
| **solc** | Solidity compilation for deployment |

### Data & Infrastructure
| Technology | Purpose |
|---|---|
| **PostgreSQL 18** | Authoritative operational database. 25+ tables, native enums, JSONB audit payloads, check constraints |
| **Docker Compose** | PostgreSQL container orchestration for development |
| **GitHub Actions** | CI pipeline: lint → typecheck → migrate → test against live PostgreSQL |
| **Open-Meteo** | Real weather model data for solar irradiance and cloud cover |

### Testing
| Technology | Purpose |
|---|---|
| **pytest** | Backend unit, integration, and API tests with disposable databases |
| **Vitest** | Frontend unit tests |
| **Playwright** | End-to-end browser tests (multi-user, desktop + mobile, real EVM verification) |
| **Ruff** | Linting and formatting |
| **mypy** | Static type checking with strict mode on application code |

---

## Engineering Highlights

### Boundary validation everywhere
Every external engine — matching, forecasting, grid solver, pricing, settlement calculator — is a Protocol. Its output is **validated at the boundary before the application trusts it**. A matching engine that over-fills an order, a pricing engine whose components don't sum to the total, or a grid solver that reports `SAFE` while its own metrics breach limits is caught with a named, attributable error — not silently accepted.

### Canonical audit serialization
Audit events are serialized deterministically before hashing. `Decimal` is rendered as a plain string (never `float`), `datetime` is normalized to UTC microseconds, keys are sorted recursively. This means equivalent events always produce the same bytes, making integrity verification reproducible across time and systems.

### Concurrency-safe audit chain
Two events appended concurrently both read the same chain head. The second loses on a `UNIQUE` constraint on `previous_hash` and must retry. The **database refuses to let the chain fork** — correctness is enforced by PostgreSQL, not by the application hoping it won't happen.

### Transaction boundaries as architecture
Each phase owns its transaction boundary explicitly. Settlement is a single transaction containing reconciliation, settlement row, and audit event. If the audit append fails, the business operation fails with it — audit failures are never swallowed. Ledger publication, by contrast, is outside the transaction: a publisher outage cannot stop a trade from settling.

### Honest grid validation
A network element with no recorded thermal rating produces a loading metric of `None`, not a guessed default. The `resolve_status` policy downgrades `SAFE` to `UNKNOWN` for any network containing unrated elements. The honest answer — "this element's thermal state is unknown" — is preserved through the entire pipeline.

### Reproducible grid inputs
Every grid validation stores a SHA-256 `input_hash` of the exact network model, limits, interval, and injections that produced the result. An identical scenario is recognizable, and the result is tied to its precise inputs.

### Formula versioning
Every price breakdown stores its `formula_version`. When the pricing formula changes, prices already stored remain explainable under the formula that produced them.

### No silent data loss
Telemetry readings are never dropped. A stale reading is recorded as `stale`, a duplicate as `duplicate`, a gap as `missing`. The quality status travels with the reading through the entire pipeline — a forecast built on data the platform itself doesn't trust would launder that distrust into a prediction.

---

## API Overview

All endpoints are versioned under `/api/v1`. OpenAPI documentation is auto-generated at `/docs` in development.

| Area | Method | Endpoint | Purpose |
|---|---|---|---|
| **Health** | `GET` | `/health/live` | Liveness probe |
| **Health** | `GET` | `/health/ready` | Readiness probe (includes DB check) |
| **Auth** | `POST` | `/api/v1/auth/login` | Credential-based session login |
| **Auth** | `POST` | `/api/v1/auth/logout` | Session termination |
| **Users** | `GET` | `/api/v1/users/{id}` | User profile |
| **Assets** | `GET` | `/api/v1/sites/{id}/assets` | Energy assets for a site |
| **Telemetry** | `POST` | `/api/v1/telemetry/readings` | Ingest meter readings |
| **Telemetry** | `GET` | `/api/v1/sites/{id}/telemetry` | Retrieve readings for a site |
| **Forecasts** | `POST` | `/api/v1/forecasts/runs` | Execute a forecast |
| **Forecasts** | `GET` | `/api/v1/sites/{id}/forecasts` | Forecast points for a site |
| **Forecasts** | `GET` | `/api/v1/sites/{id}/surplus` | Available surplus for a site |
| **Market** | `POST` | `/api/v1/market/sessions` | Open a market session |
| **Market** | `POST` | `/api/v1/market/orders` | Place a buy or sell order |
| **Market** | `POST` | `/api/v1/market/sessions/{id}/clear` | Clear a session (match orders) |
| **Market** | `GET` | `/api/v1/market/sessions/{id}/trades` | List trades for a session |
| **Pricing** | `POST` | `/api/v1/pricing/quote` | Price a scenario (stateless) |
| **Pricing** | `POST` | `/api/v1/trades/{id}/price` | Price and store a breakdown |
| **Pricing** | `GET` | `/api/v1/trades/{id}/price-breakdown` | Retrieve stored breakdown |
| **Settlement** | `POST` | `/api/v1/trades/{id}/reconcile` | Compare actual vs committed |
| **Settlement** | `POST` | `/api/v1/trades/{id}/settle` | Reconcile and settle |
| **Settlement** | `GET` | `/api/v1/settlements/{id}` | Retrieve a settlement |
| **Audit** | `GET` | `/api/v1/audit/entities/{type}/{id}` | Entity audit timeline |
| **Audit** | `GET` | `/api/v1/audit/verify` | Verify chain integrity |
| **Audit** | `POST` | `/api/v1/audit/anchor/{type}/{id}` | Anchor event to blockchain |
| **Workspace** | `POST` | `/api/v1/workspace/...` | Connected demonstration orchestration |
| **Household** | `GET` | `/api/v1/household/dashboard` | Household energy dashboard data |
| **WebSocket** | `WS` | `/ws` | Real-time event stream |

---

## Data Model

25+ PostgreSQL tables organized by domain:

```mermaid
erDiagram
    User ||--o{ Site : owns
    User ||--o{ Order : places
    User ||--o{ Consent : grants
    User ||--o| UtilityAccount : has
    User ||--o| LoginCredential : authenticates
    Site ||--o{ Meter : contains
    Site ||--o{ EnergyAsset : registers
    Site ||--o{ TelemetryReading : generates
    Site ||--o{ ForecastPoint : forecasted
    Meter ||--o{ TelemetryReading : measures
    ForecastRun ||--o{ ForecastPoint : produces
    MarketSession ||--o{ Order : accepts
    Order }o--|| Trade : matched_buy
    Order }o--|| Trade : matched_sell
    Trade ||--o| GridValidationRun : validated
    Trade ||--o| PriceComponents : priced
    Trade ||--o{ MeterReconciliation : reconciled
    Trade ||--o{ Settlement : settled
    Trade ||--o{ AuditEventRecord : audited
    GridNode ||--o{ GridNode : parent_child
    AuditEventRecord ||--o| AuditEventRecord : chain_link
    Settlement ||--o| Receipt : receipted
```

**Key entities:**

| Entity | Table | Purpose |
|---|---|---|
| `User` | `users` | Consumer, prosumer, operator, regulator, admin |
| `Site` | `sites` | Physical location with GPS, grid connection |
| `Meter` | `meters` | Smart meter with serial, verification level |
| `EnergyAsset` | `energy_assets` | PV panels, batteries, EVs with rated capacity |
| `GridNode` | `grid_nodes` | Network topology — substation, transformer, connection point |
| `TelemetryReading` | `telemetry_readings` | 15-min interval readings with quality status |
| `ForecastRun` | `forecast_runs` | Forecast execution record with provider and status |
| `ForecastPoint` | `forecast_points` | Per-interval predictions with confidence bounds |
| `MarketSession` | `market_sessions` | Day-ahead session lifecycle |
| `Order` | `orders` | Buy/sell intent with delivery window and price limit |
| `Trade` | `trades` | Matched trade with clearing price and status |
| `GridValidationRun` | `grid_validation_runs` | Power-flow result with voltage/loading metrics |
| `PriceComponents` | `price_components` | 5-component breakdown with formula version |
| `MeterReconciliation` | `meter_reconciliations` | Actual vs committed with tolerance decision |
| `Settlement` | `settlements` | Final accounting with buyer/seller amounts |
| `AuditEventRecord` | `audit_events` | Chained event with hash, payload, and optional anchor |
| `Receipt` | `receipts` | Blockchain-anchored settlement evidence |

---

## Security & Data Integrity

| Mechanism | Implementation |
|---|---|
| **Authentication** | Cookie-based sessions with `LoginCredential` and hashed passwords |
| **Authorization** | Role-based access (consumer, prosumer, operator, admin). Legacy write endpoints return `410 Gone`. |
| **CSRF protection** | `X-Requested-With: UrjaSetu` header required on mutations, origin verification |
| **Rate limiting** | Auth endpoints: 20 attempts per IP per 60 seconds |
| **CORS** | Explicit origin allowlist — no wildcards with credentials |
| **Input validation** | Pydantic schemas on every endpoint. Database `CHECK` constraints as safety net. |
| **Secrets management** | `DATABASE_URL` has no default — process refuses to start without it. Passwords never logged. `safe_database_url()` redacts credentials. |
| **Audit integrity** | SHA-256 chained events. Canonical serialization prevents hash drift. `UNIQUE` constraint on `previous_hash` prevents chain forks. |
| **Database enforcement** | PostgreSQL `CHECK` constraints on prices, quantities, and ledger balance. `NOT NULL` on required fields. Native enum types. |
| **Blockchain verification** | On-chain receipt hash compared against database evidence. Conflicts are raised, not silently accepted. |

---

## Repository Structure

```
urjasetu/
├── backend/
│   ├── app/
│   │   ├── adapters/          # External system boundaries
│   │   │   ├── forecast/      #   Baseline solar/load provider
│   │   │   ├── grid/          #   Power Grid Model wrapper (sole PGM import)
│   │   │   ├── ledger/        #   EVM publisher + local file publisher
│   │   │   └── meter/         #   CSV, simulator, and contract adapters
│   │   ├── api/
│   │   │   └── v1/            # Versioned REST endpoints (13 route modules)
│   │   ├── core/              # Config, error hierarchy, structured logging
│   │   ├── db/
│   │   │   └── models/        # SQLAlchemy ORM (12 model modules)
│   │   ├── domain/
│   │   │   ├── enums.py       # 35+ domain enumerations
│   │   │   ├── interfaces/    # Typed Protocols for all engines/providers
│   │   │   └── policies/      # Pure business rules (12 policy modules)
│   │   ├── repositories/      # Data access layer (11 repository modules)
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── services/          # Orchestration layer (16 service modules)
│   │   └── main.py            # Application factory and middleware
│   ├── alembic/               # Database migrations
│   ├── scripts/               # Seed and import utilities
│   └── tests/
│       ├── unit/              # Adapter and policy tests
│       ├── integration/       # Phase-by-phase PostgreSQL tests
│       ├── api/               # HTTP endpoint tests
│       └── forecast/          # Provider contract and surplus tests
├── frontend/
│   ├── src/
│   │   ├── features/          # Page-level components
│   │   │   ├── workspace/     #   Connected dashboard (11 files)
│   │   │   ├── market/        #   Marketplace
│   │   │   ├── grid/          #   Grid monitor (React Flow)
│   │   │   ├── trades/        #   Trade tracking
│   │   │   ├── settlements/   #   Settlement statements
│   │   │   ├── audit/         #   Blockchain receipts
│   │   │   ├── community/     #   Community view
│   │   │   ├── energy/        #   Energy monitoring
│   │   │   ├── forecasts/     #   Forecast visualization
│   │   │   ├── overview/      #   Dashboard overview
│   │   │   └── settings/      #   Profile & preferences
│   │   ├── components/        # Shared UI (charts, tables, primitives)
│   │   ├── lib/               # API client and utilities
│   │   └── styles/            # CSS tokens and app styles
│   └── tests/                 # Playwright E2E + visual tests
├── blockchain/
│   ├── ReceiptRegistry.sol    # Solidity smart contract
│   ├── deploy.mjs             # Compile + deploy script
│   └── test.mjs               # Blockchain integration tests
├── data/synthetic/            # Seed data (users, meters, grid nodes, sites)
├── docs/                      # 17 design documents
├── evaluation/                # Forecast accuracy evaluation
├── scripts/                   # Dev tooling (bootstrap, verify chain, browser tests)
├── docker-compose.yml         # PostgreSQL service
├── pyproject.toml             # Python project + tooling configuration
├── Makefile                   # Developer commands
└── .github/workflows/         # CI pipeline
```

---

## Local Development

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.12 |
| Node.js | ≥ 22.12 |
| PostgreSQL | 18 (or use Docker Compose) |
| Make | any |
| Docker | for PostgreSQL container (optional if PostgreSQL is installed natively) |

### Installation

```bash
# Clone the repository
git clone https://github.com/PatelVedant-20/UrjaSetu.git
cd UrjaSetu

# Configure environment
cp .env.example .env        # Adjust DATABASE_URL if needed

# Backend
make install                 # Creates venv, installs runtime + dev deps

# Frontend
npm --prefix frontend ci

# Blockchain (for EVM anchoring)
npm --prefix blockchain ci

# Database
make up                      # Starts PostgreSQL via Docker Compose
make migrate                 # Applies all Alembic migrations
make bootstrap               # Seeds the fictional Gujarat community
```

### Environment Variables

```env
# Application
APP_ENV=development
APP_NAME=UrjaSetu
API_V1_PREFIX=/api/v1
LOG_LEVEL=INFO

# PostgreSQL
DATABASE_URL=postgresql+psycopg://urjasetu:urjasetu@localhost:5432/urjasetu
POSTGRES_DB=urjasetu
POSTGRES_USER=urjasetu
POSTGRES_PASSWORD=urjasetu

# Connection pool
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# Simulation
SIMULATION_WORKER_ENABLED=true
BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545

# Optional: Gemini AI assistant
# GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.8-flash
```

---

## Run the Project

### All-in-one (recommended)

```bash
make demo
# Starts: PostgreSQL migration, community bootstrap,
# Ganache blockchain, API server, Vite frontend
# Open http://127.0.0.1:5173
```

### Separate terminals

```bash
# Terminal 1: Database + migrations
make up && make migrate bootstrap

# Terminal 2: Local blockchain
npm --prefix blockchain run node
# (after chain starts, in another terminal:)
npm --prefix blockchain run deploy

# Terminal 3: Backend API
make dev                    # http://localhost:8000 (with auto-reload)

# Terminal 4: Frontend
npm --prefix frontend run dev   # http://localhost:5173
```

### API documentation

Open **http://localhost:8000/docs** for interactive Swagger UI (development only).

---

## Testing

```bash
# Backend: unit + integration + API tests (uses disposable PostgreSQL databases)
make test

# Linting and type checking
make lint                   # Ruff check + format verification
make typecheck              # mypy with strict settings on app/

# Frontend: TypeScript check, unit tests, production build
make test-web

# Blockchain: Solidity + Python JSON-RPC integration
make test-chain             # Requires running local EVM

# E2E browser tests: multi-user journey with real EVM verification
make test-browser           # Creates disposable DB + separate API/UI on ports 8001/5174

# Full verification gate
make check                  # lint + typecheck + test
make verify                 # database up + migrate + test
```

**Test coverage spans:**
- Adapter contracts (Power Grid Model, baseline forecast, telemetry CSV, simulator)
- Policy logic (matching, surplus, pricing, grid limits, audit chain, settlement)
- Phase-by-phase integration tests (Phase 0–5) against live PostgreSQL
- API endpoint tests with HTTP client
- Connected workspace orchestration tests
- Forecast provider contract validation
- Two-user browser journey with real blockchain receipt verification

---

## Demo User Journey

The sign-in screen provides **Quick Access Accounts** (all use password `Sunshine2026!`):

| Account | Role | Email |
|---|---|---|
| **Asha Patel** | Solar owner, 6 kW PV | asha@urjasetu.demo |
| **Ravi Shah** | Energy buyer | ravi@urjasetu.demo |
| **Community Operator** | Supervision & dev controls | operator@urjasetu.demo |

### As a Solar Producer (Asha)

1. **Sign in** → land on **My Energy** with live generation/consumption charts
2. Power and charts refresh every 5 seconds. Toggle Live / Last hour / Last 24 hours.
3. Navigate to **Marketplace** → **Sell energy** → Create order for tomorrow's slot
4. System verifies: eligible identity ✓, forecast surplus ✓, order shape ✓
5. Watch the order appear in the book. When a buyer matches, the trade clears.
6. Grid validation runs automatically (feeder topology, voltage, loading).
7. Dynamic pricing calculates the effective price with all 5 components.
8. When the real 15-minute delivery interval finishes, settlement processes automatically.
9. View **Settlements** for credits, debits, savings. Export to CSV.
10. **Blockchain receipts** → **Verify on blockchain** → confirms receipt hash on-chain.

### As an Energy Buyer (Ravi)

1. **Sign in** in a separate browser / private window → **My Energy**
2. **Marketplace** → **Buy energy** → Create order with max price and delivery slot
3. See Asha's sell offer appear in real-time (WebSocket)
4. Match the trade → clearing executes
5. Track progress in **My Trades** — proposed → validated → priced → settled
6. **Settlements** shows the debit, savings comparison vs utility rate

### Registering a New Household

Register with monthly usage, occupants, appliances, city, and rooftop info. The system generates personalized 30-day starting history, and the new node appears in everyone's **Grid monitor** and **Community** view.

---

## What Makes UrjaSetu Different?

### A typical P2P energy marketplace
```
Producer ──→ Buyer
         (that's it)
```

### UrjaSetu
```
Producer
    ↓
Forecast (is there actually surplus energy?)
    ↓
Local Market (who wants it, at what price?)
    ↓
Grid Feasibility (can the network handle the transfer?)
    ↓
Dynamic Pricing (what should this trade actually cost?)
    ↓
Metered Settlement (what was actually delivered vs committed?)
    ↓
Auditable Trust Layer (can anyone verify this independently?)
```

The differentiator is not any single feature — it's the **combination**: energy intelligence + local market coordination + grid-aware validation + transparent pricing + metered settlement + independently verifiable audit.

Each layer uses the output of the previous layer and never re-derives it. Pricing reads the grid result, not the network topology. Settlement reads the effective price, not the clearing price. The audit records what happened, never what should have happened.

---

## Architecture Decisions

| Decision | Rationale |
|---|---|
| **Services contain no algorithms** | A service orchestrates — it calls an engine, validates its output, and records the result. The algorithm lives in a policy or adapter, independently testable. |
| **Engines are Protocols, not imports** | `MatchingEngine`, `ForecastProvider`, `GridEngine`, `PricingEngine`, `SettlementCalculator` — all typed interfaces. Swapping an implementation changes one adapter, not every service. |
| **Global audit chain, not per-entity** | Deleting an entire entity's history is undetectable in a per-entity chain. A global chain makes removing *any* event break verification. |
| **Ledger anchor outside the transaction** | A blockchain outage must never block a trade from settling. The authoritative record is in PostgreSQL. |
| **Clearing price ≠ effective price** | The Phase 4 clearing price is preserved as the market baseline. The Phase 6 effective price — with time, congestion, imbalance, and renewable components — is what settlement pays against. |
| **Forecast surplus gates selling** | A sell order that exceeds available surplus is rejected at placement, not discovered at delivery. |
| **Power Grid Model exact-pinned** | `power-grid-model==1.13.162`. A solver patch can change a validation result, and a past grid decision must stay reproducible. |
| **No `float` in audit payloads** | A price that went through binary floating point before hashing would be a different number than the one the platform used. `Decimal` is mandatory. |

---

## Current Status

```
🟢 Core architecture & domain model         Implemented
🟢 Identity, sites, meters, energy assets   Implemented
🟢 Telemetry ingestion with quality policy   Implemented
🟢 Solar & load forecasting (baseline)       Implemented
🟢 Surplus calculation                       Implemented
🟢 Day-ahead marketplace with matching       Implemented
🟢 Power-flow grid validation (PGM)          Implemented
🟢 5-component dynamic pricing               Implemented
🟢 Metered settlement & reconciliation       Implemented
🟢 SHA-256 chained audit with verification   Implemented
🟢 Blockchain anchoring (local EVM)          Implemented
🟢 Real-time WebSocket event bus             Implemented
🟢 Connected household dashboard             Implemented
🟢 AI energy assistant                       Implemented
🟢 CI pipeline (GitHub Actions)              Implemented
🟢 Multi-user E2E browser tests              Implemented
🟡 Open-Meteo weather integration            Implemented (simulated profile context)
🟡 Forecast provider ecosystem               Integration-ready (pluggable interface)
🟡 External grid data sources                Integration-ready (adapter boundary)
🟡 Public blockchain deployment              Integration-ready (chain ID restricted to 1337)
🔴 Physical meter/inverter integration       Planned
🔴 Utility/DISCOM verification               Planned
🔴 Real payment rails                        Planned
🔴 Production identity (password recovery)   Planned
```

---

## Limitations & Assumptions

**These are explicitly stated because credibility comes from honesty, not from hiding gaps.**

| Limitation | Detail |
|---|---|
| **Simulated energy** | Meter readings are profile-driven simulations, not physical measurements |
| **Simulated currency** | INR amounts are accounting entries, not connected to payment infrastructure |
| **Fictional community** | The Gujarat households, feeder, and grid topology are synthetic seed data |
| **Local blockchain only** | The EVM runs locally (Ganache, chain ID 1337). The deploy script **refuses** to run on other networks. |
| **Baseline forecast** | The provider uses sinusoidal solar curves + Open-Meteo cloud cover, not ML models |
| **Default line parameters** | Power Grid Model uses typical Indian LV distribution values (R=0.30 Ω/km, X=0.10 Ω/km) — not surveyed conductor data |
| **Provisional pricing coefficients** | Tariff bands and component weights are placeholders pending regulatory input |
| **Day-ahead only** | Real-time and intra-day market modes are not implemented |
| **No production auth** | No email verification, password recovery, or OAuth integration |

---

## Roadmap

### Near Term
- Advanced forecast providers (time-series ML models for solar and load)
- Improved forecast accuracy evaluation and benchmarking
- Enhanced UI/UX polish and accessibility
- Expanded test coverage and performance benchmarks

### Medium Term
- Real smart-meter integration (bidirectional SunSpec / DLMS-COSEM)
- Weather-indexed forecast correction
- Intra-day market sessions
- Multi-feeder grid topology with inter-feeder constraints
- Advanced matching algorithms (welfare-maximizing, multi-interval)

### Long Term
- DISCOM/utility integration for identity verification and net-metering
- Real payment rails (UPI/NPCI integration for settlement)
- Public blockchain deployment (Polygon/Base) with gas optimization
- Multi-community federation with cross-community trading
- Automated demand response integration
- Regulatory compliance module for Indian electricity trading regulations

---

## Production Considerations

Moving from this prototype to production would require:

| Area | What's needed |
|---|---|
| **Smart meters** | Bidirectional integration with certified AMI infrastructure |
| **Grid operator coordination** | Real feeder topology data, conductor parameters, live SCADA feeds |
| **Regulatory compliance** | CERC / SERC approval for peer-to-peer energy trading under Indian electricity regulations |
| **Identity verification** | Aadhaar-linked KYC, DISCOM account verification, utility bill cross-reference |
| **Payment infrastructure** | Escrow, UPI settlement rails, GST computation, invoicing |
| **Data quality** | Surveyed conductor impedances instead of default parameters |
| **Cybersecurity** | Penetration testing, SOC 2 compliance, encrypted meter-to-cloud channels |
| **Reliability** | HA PostgreSQL (Patroni/CloudNativePG), Redis cache, message queue for event bus |
| **Monitoring** | OpenTelemetry tracing, Prometheus metrics, PagerDuty alerting |
| **Privacy** | DPDPA compliance, data minimization, consent management |

This list demonstrates that the team understands the distance between a working prototype and a deployed energy platform — and has designed the architecture so that each integration changes an adapter or policy, not the core pipeline.

---

## Contributing

```bash
# After cloning and installing:
make check        # lint + typecheck + test (must pass before PR)
make format       # auto-fix formatting
```

All backend code requires type hints (`disallow_untyped_defs`). Ruff enforces style. mypy enforces types. PostgreSQL enforces constraints. Tests run against real databases, not mocks.

---

## License

See the repository for license terms.

---

<p align="center">
  <strong>UrjaSetu treats local renewable energy not as isolated generation, but as a coordinated, validated, and auditable market.</strong>
  <br/><br/>
  Forecast it. Match it. Validate the grid. Price it transparently. Settle it honestly. Prove it on-chain.
</p>
