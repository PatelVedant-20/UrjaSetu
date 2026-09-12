# 08 — AI Agent Guardrails / Team Operating Protocol

## Non-Negotiable Git Rules

### Before work
```bash
git checkout main
git pull
git checkout -b phase-X-member-name
```

### During work
- Stay on your branch.
- Pull latest `main` only when Yagnik instructs you to do so.
- Do not merge other branches.
- Do not commit.
- Do not push.
- Do not force-push.

### Completion handoff
The agent must return:
1. files changed
2. design decisions
3. tests run and results
4. known limitations
5. any migration/API/schema implications

Then **the human user/Yagnik performs the commit**.

## Architecture Guardrails

An agent must stop and ask before:
- changing a locked table name
- changing a public endpoint contract
- adding a new dependency to `pyproject.toml`
- introducing Redis/Kafka/NATS
- introducing a blockchain dependency
- changing PostgreSQL schema outside the assigned phase
- replacing SQLAlchemy/Alembic/FastAPI
- moving logic between domain/service/adapter layers
- changing units or time conventions

## Directory Ownership

### Yagnik
Primary authority:
- `backend/app/core/`
- `backend/app/db/`
- `backend/app/domain/interfaces/`
- `backend/app/services/` when core integration is involved
- `backend/app/api/v1/router.py`
- `docker-compose.yml`
- `pyproject.toml`
- `alembic/`
- architecture docs

### Manthan
Normally implementation/policy scope:
- explicitly assigned adapter files
- isolated domain policy files
- API tests when assigned

Must not modify core DB/session/migrations unless explicitly assigned.

### Siddhant
Primarily tests/fixtures:
- `backend/tests/`
- assigned fixture directories

Must not modify production logic to “make tests pass” without explicit assignment.

### Vedant
Primarily data/scenario/support scope:
- `data/`
- `scripts/` when assigned
- demo scenario fixtures
- assigned integration tests

Must not redesign backend contracts.

## No AI Agent May

- install arbitrary packages because they seem useful
- copy entire external repositories into the project without approval
- commit secrets
- modify `.env` with real credentials
- delete migrations
- bypass failing tests with skips unless explicitly justified
- change expected behavior simply to satisfy a failing test
- introduce hidden background processes
- create “temporary” duplicate schemas

## Definition of Done

A phase is not done until:
- code is formatted/linted
- unit/integration tests pass
- API schema is consistent
- DB migrations work from empty state
- no secrets are present
- diff is limited to assigned scope
- Yagnik validates integration
