# 02 — Technology Stack Decision

> **Status: LOCKED for MVP**

## Decision Summary

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Strong fit for data science, grid libraries and clean REST/WebSocket APIs |
| ORM / DB access | SQLAlchemy 2.x | Mature relational mapping and explicit control |
| Schema validation | Pydantic 2.x | Strong API/domain validation and serialization |
| Migrations | Alembic | Versioned PostgreSQL schema changes |
| Database | PostgreSQL 18.x | Reliable relational core; excellent constraints/indexing and JSONB when needed |
| Time series | PostgreSQL first | Avoid premature TimescaleDB dependency; add partitioning/extension only after profiling |
| HTTP | REST/JSON | CRUD, commands, batch ingestion and business operations |
| Realtime | WebSocket | Dashboard updates, market/grid/telemetry streams |
| Background jobs | Python service/application scheduler initially | Keep deployment simple; introduce task queue only when justified |
| Cache/pub-sub | Redis later | Only when multi-process realtime/background scaling requires it |
| Message bus | None in Phase 0 | Avoid Kafka complexity; add MQTT/Kafka/NATS only with measured need |
| Grid analysis | Power Grid Model | Distribution power flow/state estimation/short circuit |
| Device interoperability | pySunSpec2 + vendor adapters | Standardized device integration path |
| Forecasting | Provider interface; initial simple model | Algorithms must be swappable; later XGBoost/LightGBM/OpenSTEF can implement provider |
| Weather | Pluggable weather provider | Avoid coupling to one API |
| Audit ledger | PostgreSQL audit log first; optional Hyperledger Fabric | Blockchain should not become the operational DB |
| Frontend | React + TypeScript + Vite | Interactive SPA, easy API/WebSocket integration |
| Frontend data | TanStack Query | Server-state caching/synchronization |
| Frontend local state | Zustand only where needed | Keep state small and explicit |
| Charts | ECharts or Recharts | Interactive telemetry/market/grid visualizations |
| API client | Generated from OpenAPI later | Prevent frontend/backend schema drift |
| Auth | JWT/OIDC-compatible adapter | Avoid locking domain code to one identity provider |
| Local orchestration | Docker Compose | Reproducible team setup |
| CI | GitHub Actions | lint/test/migration checks |
| Testing | Pytest + HTTPX/TestClient | Backend/domain/API coverage |
| Code quality | Ruff + mypy (targeted) | Fast Python linting/formatting and type safety |

## Why FastAPI

FastAPI directly supports SQL-backed applications and WebSockets, and exposes OpenAPI documentation/validation. It fits the Python-heavy grid, data and forecasting ecosystem.

## Why PostgreSQL instead of NoSQL

The domain is highly relational:
- user -> site -> meter -> asset
- order -> trade -> settlement
- trade -> grid-validation run
- market session -> orders
- actual telemetry -> forecast/reconciliation

Strong constraints and transactions are valuable. JSONB can be used only for genuinely variable external payloads.

## Why PostgreSQL first for time series

Hackathon scale does not justify an additional time-series platform immediately. We can index/partition telemetry and upgrade later without changing the domain interface.

## REST vs WebSocket

### REST is authoritative for writes
Use REST for:
- creating orders
- registering assets
- ingesting readings
- creating market sessions
- requesting forecasts
- starting validation
- settlement queries

### WebSocket is delivery-only for realtime UX
Use WebSocket for:
- live market snapshots
- grid status
- trade-state notifications
- telemetry updates
- demo events

Do not use WebSocket as the only write path for core business transactions.

## Version Pinning

Pin runtime major/minor versions in Docker and lock Python/Node dependencies. Do not rely on `latest` tags in team development.

Suggested baseline:
- Python 3.12
- PostgreSQL 18.x
- Node 22 LTS for future frontend work

Exact patch versions should be pinned in lock/config files during Phase 0.

## Architecture Style

**Modular monolith**, not microservices.

We keep domain boundaries equivalent to future services, but deploy one backend during the hackathon. This gives us simpler local development and fewer network/failure points while preserving a path to later extraction.
