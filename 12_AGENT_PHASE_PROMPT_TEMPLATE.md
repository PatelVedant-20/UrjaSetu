# 12 — Agent Phase Prompt Template

Copy this file into an AI coding agent at the start of a phase, replacing bracketed fields.

---

## Context

You are contributing to **GridShare**, HackOut's grid-aware local renewable-energy marketplace.

Read before editing:
- `docs/00_PROJECT_BIBLE.md`
- `docs/01_FINAL_ARCHITECTURE.md`
- `docs/02_TECH_STACK.md`
- `docs/03_REPOSITORY_STRUCTURE.md`
- `docs/04_DATA_MODEL.md`
- `docs/05_API_SPEC.md`
- `docs/06_OPEN_SOURCE_INTEGRATION.md`
- `docs/07_CODING_PHASES.md`
- `docs/08_AGENT_GUARDRAILS.md`

## Your Assignment

Phase: `[PHASE NUMBER]`
Member: `[YAGNIK / MANTHAN / SIDDHANT / VEDANT]`
Owned paths: `[EXACT DIRECTORIES/FILES]`
Forbidden paths: `[EXACT DIRECTORIES/FILES]`

## Hard Rules

1. Do not commit.
2. Do not merge.
3. Do not push.
4. Do not modify `main`.
5. Do not create a second architecture.
6. Do not change locked contracts unless Yagnik explicitly approves it.
7. Do not add dependencies unless the phase assignment explicitly allows it.
8. Do not copy an external repository wholesale.
9. Keep all external libraries behind the appropriate adapter boundary.
10. Do not change database schema/migrations outside your assigned scope.

## Before Coding

1. Confirm current branch is a phase-specific branch from verified `main`.
2. Inspect the existing implementation; do not recreate files that already exist.
3. Read the relevant phase section of `07_CODING_PHASES.md`.
4. Identify interfaces/contracts you must preserve.

## During Coding

- Make the smallest change satisfying the phase.
- Prefer existing utilities and interfaces.
- Keep business rules out of routers.
- Keep external libraries out of the domain layer.
- Add/modify tests with the feature.
- Avoid unrelated formatting/reorganization.

## Before Handoff

Run the phase-required tests and report:

```text
PHASE:
MEMBER:
BRANCH:
FILES CHANGED:
WHAT I IMPLEMENTED:
TESTS RUN:
TEST RESULT:
DB/MIGRATION IMPACT:
API IMPACT:
DEPENDENCY IMPACT:
KNOWN LIMITATIONS:
POTENTIAL CONFLICTS:
```

Stop after handoff. The human integrator performs commit/merge.
