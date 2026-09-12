# 09 — Phase 0 Setup: Backend + PostgreSQL Foundation

> **Owner: Yagnik**
>
> This is the first implementation phase. No frontend. No market logic. No grid logic. No forecasting. No blockchain.

## Objective

Create a reproducible development foundation in which any team member can clone the repository and run:

`FastAPI -> SQLAlchemy -> PostgreSQL -> Alembic`

with stable API conventions and test infrastructure.

## Prerequisites

Install/verify:
- Git
- Docker + Docker Compose plugin
- Python 3.12
- a code editor/IDE
- optional: `uv` or another Python environment manager

Frontend tools are intentionally deferred.

## Step 1 — Initialize Repository

```bash
git init
git branch -M main
mkdir -p backend/app backend/tests docs data scripts
```

Protect `main` on GitHub/GitLab before team development.

## Step 2 — Create Python Project

Create `pyproject.toml` with locked runtime/development dependencies.

Core runtime packages:
- fastapi
- uvicorn
- sqlalchemy
- psycopg
- pydantic
- pydantic-settings
- alembic

Development:
- pytest
- httpx
- ruff
- mypy

Do not add grid/ML/blockchain dependencies in Phase 0.

## Step 3 — Docker PostgreSQL

Create `docker-compose.yml` containing only:
- PostgreSQL
- optional pgAdmin only if the team genuinely needs it

Use environment variables:
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`

Use a named volume for local persistence.

## Step 4 — Environment Configuration

Create `.env.example`.

Example variables:

```env
APP_ENV=development
APP_NAME=UrjaSetu
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+psycopg://urjasetu:urjasetu@db:5432/urjasetu
LOG_LEVEL=INFO
```

Never commit a real `.env` file.

## Step 5 — FastAPI Application

Create:
- `backend/app/main.py`
- `backend/app/core/config.py`
- `backend/app/core/logging.py`
- `backend/app/api/v1/router.py`

Expose:
- `/health`
- `/health/ready`
- `/api/v1/meta`

Swagger/OpenAPI should be available in development.

## Step 6 — PostgreSQL Connection

Implement:
- engine creation
- session factory
- dependency for DB session
- clean startup/shutdown handling

Database access must occur through the application DB layer, never directly inside routers.

## Step 7 — SQLAlchemy Base

Create a common declarative base and conventions for:
- UUID primary keys
- `created_at`
- `updated_at`
- naming conventions for constraints/indexes

Do not create the complete UrjaSetu schema yet.

## Step 8 — Alembic

Initialize Alembic and configure it to use the SQLAlchemy metadata.

First migration should create only a tiny verification table, for example:
`system_metadata`

Then prove:

```bash
alembic upgrade head
```

works against an empty PostgreSQL database.

## Step 9 — Error Contract

Create a standard API error model:

```json
{
  "error": {
    "code": "...",
    "message": "...",
    "details": {},
    "request_id": "..."
  }
}
```

## Step 10 — Test Infrastructure

Create:
- app test fixture
- DB test fixture
- health test
- DB connectivity test
- migration smoke test

The test suite must not require manual database edits.

## Step 11 — Developer Commands

Add a Makefile or equivalent:

```text
make dev
make up
make down
make migrate
make test
make lint
make format
```

Commands may be implemented differently, but team behavior must be consistent.

## Step 12 — CI

CI should run on pull requests:
1. install dependencies
2. lint
3. tests
4. build/start backend where practical
5. run migration smoke check

CI should not deploy anything in Phase 0.

## Step 13 — Team Verification

Every member must independently:
1. clone
2. create local environment
3. start PostgreSQL
4. run migrations
5. start backend
6. call health endpoint
7. run tests

A phase fails if one member cannot reproduce the setup.

## Phase 0 Folder Output

Expected minimum:

```text
backend/app/main.py
backend/app/core/config.py
backend/app/core/logging.py
backend/app/api/v1/router.py
backend/app/api/v1/health.py
backend/app/db/session.py
backend/app/db/base.py
backend/tests/integration/phase0/test_health.py
backend/tests/integration/phase0/test_db.py
backend/alembic/env.py
backend/alembic/versions/<initial_migration>.py
docker-compose.yml
.env.example
pyproject.toml
Makefile
```

## Phase 0 “Do Not Touch”

Do not implement:
- user domain models beyond smoke-test metadata
- telemetry
- forecasting
- orders
- matching
- pricing
- Power Grid Model
- WebSockets
- blockchain
- frontend

Those belong to later phases.
