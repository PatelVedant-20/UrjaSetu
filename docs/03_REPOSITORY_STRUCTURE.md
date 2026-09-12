# 03 — Repository Structure

```text
UrjaSetu/
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── docs/
│   ├── 00_PROJECT_BIBLE.md
│   ├── 01_FINAL_ARCHITECTURE.md
│   ├── 02_TECH_STACK.md
│   ├── 03_REPOSITORY_STRUCTURE.md
│   ├── 04_DATA_MODEL.md
│   ├── 05_API_SPEC.md
│   ├── 06_OPEN_SOURCE_INTEGRATION.md
│   ├── 07_CODING_PHASES.md
│   ├── 08_AGENT_GUARDRAILS.md
│   ├── 09_PHASE_0_SETUP.md
│   ├── 10_TESTING_AND_INTEGRATION.md
│   ├── 11_REGULATORY_AND_INDIA_CONTEXT.md
│   └── 12_AGENT_PHASE_PROMPT_TEMPLATE.md
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── errors.py
│   │   │   └── security.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── base.py
│   │   │   └── models/
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       ├── health.py
│   │   │       ├── users.py
│   │   │       ├── assets.py
│   │   │       ├── telemetry.py
│   │   │       ├── forecasts.py
│   │   │       ├── market.py
│   │   │       ├── grid.py
│   │   │       ├── settlement.py
│   │   │       └── audit.py
│   │   ├── schemas/
│   │   │   ├── common.py
│   │   │   ├── users.py
│   │   │   ├── assets.py
│   │   │   ├── telemetry.py
│   │   │   ├── forecasts.py
│   │   │   ├── market.py
│   │   │   ├── grid.py
│   │   │   ├── settlement.py
│   │   │   └── audit.py
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── identity_service.py
│   │   │   ├── asset_service.py
│   │   │   ├── telemetry_service.py
│   │   │   ├── forecast_service.py
│   │   │   ├── market_service.py
│   │   │   ├── grid_service.py
│   │   │   ├── pricing_service.py
│   │   │   ├── settlement_service.py
│   │   │   └── audit_service.py
│   │   ├── domain/
│   │   │   ├── enums.py
│   │   │   ├── policies/
│   │   │   └── interfaces/
│   │   └── adapters/
│   │       ├── weather/
│   │       ├── inverter/
│   │       ├── meter/
│   │       ├── forecast/
│   │       ├── grid/
│   │       └── ledger/
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── api/
├── data/
│   ├── raw/
│   ├── processed/
│   └── synthetic/
├── scripts/
│   ├── seed_dev.py
│   ├── generate_profiles.py
│   └── load_dataset.py
├── frontend/                 # DO NOT TOUCH until backend gate passes
│   └── ...
└── .github/
    └── workflows/
        └── backend-ci.yml
```

## Ownership Rules

- `backend/app/domain/` contains business rules and interfaces; no agent may create duplicate domain abstractions.
- `backend/app/services/` coordinates repositories/adapters.
- `backend/app/adapters/` is the only place where external vendors/libraries are coupled to UrjaSetu domain interfaces.
- `backend/app/api/` contains transport-layer concerns only.
- `backend/app/schemas/` contains API/input/output contracts, not SQL persistence logic.
- `backend/app/db/models/` contains persistence models only.
- `backend/alembic/versions/` is migration history. Do not edit old migrations once merged.
- `docs/` is controlled by Yagnik unless a phase explicitly assigns one file.

## No-Crossing Rule

An agent must not modify another agent's owned directory unless the phase document explicitly permits it.
