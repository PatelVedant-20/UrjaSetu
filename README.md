# UrjaSetu

**A grid-aware local renewable-energy marketplace.**

UrjaSetu predicts local supply and demand, matches renewable-energy orders,
validates every proposed trade against real distribution-grid constraints,
prices it explainably, reconciles against actual meter data and settles
auditably.

We do **not** model physical peer-to-peer electron routing. Physical delivery
stays on the existing DISCOM distribution grid; UrjaSetu is the digital layer
on top of it. See [`00_PROJECT_BIBLE.md`](docs/00_PROJECT_BIBLE.md).

---

## Status — Phase 0 (foundation)

The backend foundation is in place:

```
FastAPI -> configuration -> SQLAlchemy -> PostgreSQL -> Alembic
```

Nothing else is implemented yet. No market engine, no forecasting, no grid
simulation, no frontend — those arrive in later phases
(see [`07_CODING_PHASES.md`](docs/07_CODING_PHASES.md)).

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12 |
| Docker + Compose plugin | any current release |
| Git | any current release |
| GNU Make | any current release |

Your user needs access to the Docker daemon. Either join the `docker` group
(`sudo usermod -aG docker $USER`, then log out and back in), or pass `sudo`
through to Compose:

```bash
make up COMPOSE="sudo docker compose"
```

---

## Quickstart

```bash
git clone <repository-url> UrjaSetu
cd UrjaSetu

cp .env.example .env      # adjust if your PostgreSQL port is taken
make install              # create .venv and install dependencies
make up                   # start PostgreSQL and wait until it is healthy
make migrate              # alembic upgrade head
make test                 # full Phase 0 test suite
make dev                  # API on http://localhost:8000
```

Then check the API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
curl http://localhost:8000/api/v1/meta
```

Interactive docs: <http://localhost:8000/docs>

`make verify` runs `up`, `migrate` and `test` in sequence — the Phase 0 gate in
one command.

---

## Commands

| Command | Purpose |
|---|---|
| `make help` | List all commands |
| `make install` | Create `.venv` and install runtime + dev dependencies |
| `make up` / `make down` | Start / stop PostgreSQL (add `COMPOSE="sudo docker compose"` if needed) |
| `make logs` | Tail PostgreSQL logs |
| `make migrate` | Apply migrations (`alembic upgrade head`) |
| `make revision m="…"` | Autogenerate a migration from model changes |
| `make downgrade` | Roll back one migration |
| `make dev` | Run the API with auto-reload |
| `make test` | Run the test suite |
| `make lint` / `make format` | Check / fix formatting and lint |
| `make typecheck` | Run mypy over `backend/app` |
| `make check` | Lint + typecheck + test |
| `make verify` | `up` + `migrate` + `test` |

---

## Configuration

All configuration comes from environment variables, loaded from `.env` by
`backend/app/core/config.py`. **No credentials are hard-coded anywhere**, and
`DATABASE_URL` has no default — the process refuses to start without it.

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` / `test` / `staging` / `production` |
| `APP_NAME`, `API_V1_PREFIX`, `LOG_LEVEL` | Application basics |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT` | Read by `docker-compose.yml` |
| `DATABASE_URL` | SQLAlchemy URL used by both the app and Alembic |
| `MAINTENANCE_DATABASE_URL` | Used only by the migration smoke test |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_PRE_PING`, `DB_ECHO` | Connection pool |

`.env` is located by absolute path from `backend/app/core/config.py`, so Alembic
(run from `backend/`), uvicorn and pytest all read the same file no matter which
directory you invoke them from. Real environment variables always take
precedence over it.

Dependency versions: `pyproject.toml` pins major/minor; `requirements.lock.txt`
records the exact patch versions this phase was verified against.

`DATABASE_URL` must be a PostgreSQL URL. SQLite and other backends are rejected
at startup — PostgreSQL is the operational source of truth.

Never commit a real `.env`; it is gitignored.

---

## Layout

```
backend/app/
  main.py              FastAPI entrypoint, middleware, lifespan
  core/
    config.py          Pydantic settings — the one configuration source
    logging.py         Log setup and the request-id context
    errors.py          Error envelope and exception handlers
  api/
    deps.py            Shared dependencies (DB session, settings)
    v1/
      router.py        v1 composition root
      health.py        /health, /health/ready
      meta.py          /api/v1/meta
  db/
    base.py            Declarative base, naming conventions, shared mixins
    session.py         Engine, session factory, connectivity check
    models/            Persistence models
  schemas/
    common.py          Shared API contracts
backend/alembic/       Migration environment and history
backend/tests/         conftest fixtures + integration/phase0/
```

Layer rules are in [`03_REPOSITORY_STRUCTURE.md`](docs/03_REPOSITORY_STRUCTURE.md):
routers hold transport concerns only, business rules live in `domain/`, and
external libraries are confined to `adapters/`.

---

## API surface (Phase 0)

| Endpoint | Description |
|---|---|
| `GET /health` | Process liveness. Performs no I/O. |
| `GET /health/ready` | Verifies PostgreSQL with a real `SELECT 1`. |
| `GET /api/v1/meta` | API version, enabled integrations, market mode. |

Every non-2xx response uses the locked envelope:

```json
{
  "error": {
    "code": "DATABASE_UNAVAILABLE",
    "message": "The database is not reachable.",
    "details": {},
    "request_id": "…"
  }
}
```

Supply `X-Request-ID` on a request and it is echoed back and used as the
envelope's `request_id`.

---

## Database work

Schema changes are **migration-first**:

1. Edit or add a model under `backend/app/db/models/`.
2. Export it from `backend/app/db/models/__init__.py` (otherwise Alembic cannot see it).
3. `make revision m="describe the change"`.
4. Review the generated migration by hand.
5. `make migrate`, then `make test`.

Never edit a migration that has already been merged.

---

## Working agreements

`main` is protected. Work on a branch named `phase-<n>-<name>`, stay inside the
paths your phase assigns you, and hand the diff to Yagnik — he performs the
commit and merge. The full protocol is in
[`08_AGENT_GUARDRAILS.md`](docs/08_AGENT_GUARDRAILS.md).

---

## Project documentation

| Document | Contents |
|---|---|
| [`00_PROJECT_BIBLE.md`](docs/00_PROJECT_BIBLE.md) | Definition, principles, units, forbidden shortcuts |
| [`01_FINAL_ARCHITECTURE.md`](docs/01_FINAL_ARCHITECTURE.md) | Layers, runtime architecture, data flow |
| [`02_TECH_STACK.md`](docs/02_TECH_STACK.md) | Locked technology decisions |
| [`03_REPOSITORY_STRUCTURE.md`](docs/03_REPOSITORY_STRUCTURE.md) | Layout and ownership rules |
| [`04_DATA_MODEL.md`](docs/04_DATA_MODEL.md) | Entities, relationships, transaction boundaries |
| [`05_API_SPEC.md`](docs/05_API_SPEC.md) | REST and WebSocket contract |
| [`06_OPEN_SOURCE_INTEGRATION.md`](docs/06_OPEN_SOURCE_INTEGRATION.md) | Reuse plan and integration boundaries |
| [`07_CODING_PHASES.md`](docs/07_CODING_PHASES.md) | Phase sequence and per-member assignments |
| [`08_AGENT_GUARDRAILS.md`](docs/08_AGENT_GUARDRAILS.md) | Git rules, ownership, definition of done |
| [`09_PHASE_0_SETUP.md`](docs/09_PHASE_0_SETUP.md) | This phase, step by step |
| [`10_TESTING_AND_INTEGRATION.md`](docs/10_TESTING_AND_INTEGRATION.md) | Test pyramid and phase gates |
| [`11_REGULATORY_AND_INDIA_CONTEXT.md`](docs/11_REGULATORY_AND_INDIA_CONTEXT.md) | India / Gujarat regulatory context |
| [`12_AGENT_PHASE_PROMPT_TEMPLATE.md`](docs/12_AGENT_PHASE_PROMPT_TEMPLATE.md) | Prompt template for phase agents |
