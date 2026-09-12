# 10 — Testing and Integration Gates

## Test Pyramid

### Unit tests
Pure policy/calculation logic:
- price formula
- order validation
- matching
- forecast transforms
- reconciliation
- reliability score

### Integration tests
Component boundaries:
- service + PostgreSQL
- adapter + normalized schema
- market + grid validator
- reconciliation + settlement

### API tests
Test public contract and status codes.

### End-to-end tests
Only a few critical scenarios spanning the full workflow.

## Mandatory Scenarios

1. Valid prosumer onboarding
2. Valid consumer onboarding
3. Telemetry ingestion
4. Forecast generation
5. Buy/sell order submission
6. Successful market match
7. Safe grid validation
8. Congested grid -> reprice/reduce/shift/reject
9. Actual equals commitment
10. Actual below commitment
11. Stale telemetry -> restricted sell volume
12. Audit event creation

## Determinism

The following must be deterministic given fixed inputs and formula/model versions:
- order matching
- price calculation
- grid decision normalization
- settlement calculation

Random simulation may exist only in data-generation layers and must support a fixed seed.

## API Compatibility

When a phase modifies a response model:
- update schema docs
- update backend tests
- update OpenAPI expectations
- notify frontend is still not in use until Phase 9

## Database Rules

Every schema change:
1. SQLAlchemy model change
2. Alembic migration
3. migration test from clean DB
4. application test against migrated DB

## Integration Gate Template

Before phase sign-off Yagnik records:

```text
Phase:
Branch(es):
Features completed:
Tests:
Migration status:
API status:
Known issues:
Open risks:
Approved by Yagnik: YES/NO
```

Only `YES` allows the next phase.
