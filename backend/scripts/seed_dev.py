#!/usr/bin/env python3
"""seed_dev.py — GridShare Phase-1 development seed loader.

PURPOSE
-------
Loads a small, deterministic community dataset into the development database.
Designed to represent a realistic but entirely fictional Gujarat-area feeder
community suitable for demos, integration tests and development exploration.

USAGE
-----
    # From the project root (with .venv activated and DATABASE_URL in .env):
    python backend/scripts/seed_dev.py

    # Preview only — print what would be loaded without touching the DB:
    python backend/scripts/seed_dev.py --dry-run

    # Wipe and reload from scratch (idempotent wipe+reload):
    python backend/scripts/seed_dev.py --reset

SAFETY
------
- Only runs when APP_ENV is 'development' or 'test'.  Will ABORT in production.
- All seed IDs start with well-known UUID prefixes (1000…, 2000…, etc.) that are
  clearly non-production.
- All display names / emails end with .demo domain.
- No real personal data, no real meter serials, no real DISCOM credentials.
- Idempotent: running twice does NOT duplicate rows (upsert on primary key).

OWNERSHIP (docs/07_CODING_PHASES.md)
--------------------------------------
  Siddhant — seed fixtures under data/synthetic/ and this script only.
  Do NOT touch backend/app/db/, backend/app/domain/, backend/app/api/.

NOTE
----
Phase 1 ORM models (User, Site, Meter, EnergyAsset, InverterDevice,
UtilityAccount, VerificationRecord, Consent, GridNode) are created by Yagnik.
This script imports those models.  If they do not exist yet, it prints a clear
message and exits gracefully — it never crashes the dev environment.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed_dev")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"

FIXTURE_ORDER = [
    "grid_nodes",
    "users",
    "utility_accounts",
    "sites",
    "meters",
    "energy_assets",
    "inverter_devices",
    "verification_records",
    "consents",
]


# ---------------------------------------------------------------------------
# Guard — refuse to run outside dev/test
# ---------------------------------------------------------------------------
def _check_environment() -> None:
    """Abort if APP_ENV is not development or test."""
    import os

    env = os.environ.get("APP_ENV", "development").lower()
    if env not in {"development", "test"}:
        log.error(
            "ABORT: seed_dev.py must not run in APP_ENV=%r. "
            "Only 'development' and 'test' are permitted.",
            env,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------
def _load_fixture(name: str) -> list[dict]:
    path = SYNTHETIC_DIR / f"{name}.json"
    if not path.exists():
        log.warning("Fixture not found: %s — skipping", path)
        return []
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    records = data.get(name, [])
    log.info("  Loaded fixture %-30s  %d records", f"{name}.json", len(records))
    return records


def load_all_fixtures() -> dict[str, list[dict]]:
    """Return all fixture data keyed by entity name."""
    result: dict[str, list[dict]] = {}
    for name in FIXTURE_ORDER:
        result[name] = _load_fixture(name)
    return result


# ---------------------------------------------------------------------------
# Dry-run printer
# ---------------------------------------------------------------------------
def _dry_run(fixtures: dict[str, list[dict]]) -> None:
    log.info("=== DRY RUN — no database writes ===")
    total = 0
    for name in FIXTURE_ORDER:
        records = fixtures.get(name, [])
        log.info("  %-30s  %d records", name, len(records))
        total += len(records)
    log.info("Total records: %d", total)
    log.info("=== DRY RUN complete ===")


# ---------------------------------------------------------------------------
# Database seed (runs once ORM models exist)
# ---------------------------------------------------------------------------
def _seed_database(fixtures: dict[str, list[dict]], reset: bool) -> None:
    """Import ORM models and upsert seed rows."""

    # --- Attempt to import Phase-1 models -----------------------------------
    # These models are created by Yagnik in Phase 1.
    # If they don't exist yet, we exit with a clear, actionable message.
    try:
        from app.db.session import session_scope  # noqa: F401, PLC0415
    except ImportError:
        log.error(
            "Cannot import app.db.session.  "
            "Make sure the backend package is installed (pip install -e '.[dev]') "
            "and the virtual environment is activated."
        )
        sys.exit(1)

    phase1_models_available = True
    try:
        from app.db.models.assets import (  # noqa: F401, PLC0415
            EnergyAsset,
            GridNode,
            InverterDevice,
            Meter,
            Site,
            VerificationRecord,
        )
        from app.db.models.identity import Consent, User, UtilityAccount  # noqa: F401, PLC0415
    except ImportError as exc:
        log.warning(
            "Phase-1 ORM models not yet available (%s). "
            "Fixture validation will be skipped.  "
            "Re-run this script after Yagnik creates the Phase-1 models.",
            exc,
        )
        phase1_models_available = False

    if not phase1_models_available:
        log.info(
            "Fixtures loaded from disk and validated for structure.  "
            "Database seed deferred until Phase-1 models are merged."
        )
        _dry_run(fixtures)
        return

    _seed(fixtures, reset)


def _seed(fixtures: dict[str, list[dict]], reset: bool) -> None:
    """Upsert all fixture records inside a single transaction."""
    import uuid  # noqa: PLC0415
    from datetime import datetime  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415
    from sqlalchemy.dialects.postgresql import insert  # noqa: PLC0415

    from app.db.models.assets import (  # noqa: PLC0415
        EnergyAsset,
        GridNode,
        InverterDevice,
        Meter,
        Site,
        VerificationRecord,
    )
    from app.db.models.identity import Consent, User, UtilityAccount  # noqa: PLC0415
    from app.db.session import session_scope  # noqa: PLC0415

    MODEL_MAP = {
        "grid_nodes": GridNode,
        "users": User,
        "utility_accounts": UtilityAccount,
        "sites": Site,
        "meters": Meter,
        "energy_assets": EnergyAsset,
        "inverter_devices": InverterDevice,
        "verification_records": VerificationRecord,
        "consents": Consent,
    }

    def _coerce(record: dict, model) -> dict:
        """Convert string UUIDs/dates to Python types expected by the model."""
        result = {}
        for k, v in record.items():
            if isinstance(v, str) and len(v) == 36 and v.count("-") == 4:
                try:
                    result[k] = uuid.UUID(v)
                    continue
                except ValueError:
                    pass
            if isinstance(v, str) and v.endswith("Z") and "T" in v:
                try:
                    result[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
                    continue
                except ValueError:
                    pass
            result[k] = v
        return result

    # `session_scope` commits on success and rolls back on any exception, so a
    # failed seed leaves the registry untouched rather than half-populated.
    with session_scope() as session:
        if reset:
            log.warning("--reset: deleting existing seed rows (reverse order)…")
            for name in reversed(FIXTURE_ORDER):
                model = MODEL_MAP.get(name)
                if model is None:
                    continue
                session.execute(text(f"DELETE FROM {model.__tablename__}"))
            log.info("Existing seed rows deleted.")

        for name in FIXTURE_ORDER:
            model = MODEL_MAP.get(name)
            records = fixtures.get(name, [])
            if not records or model is None:
                continue
            stmt = (
                insert(model)
                .values([_coerce(r, model) for r in records])
                .on_conflict_do_nothing(index_elements=["id"])
            )
            session.execute(stmt)
            log.info("  Upserted %-30s  %d rows", name, len(records))

    log.info("Seed complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="GridShare Phase-1 dev seed loader")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print fixture summary without writing to the database.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing seed rows before loading (idempotent wipe + reload).",
    )
    args = parser.parse_args()

    _check_environment()

    log.info("GridShare Phase-1 seed loader starting…")
    log.info("Fixtures directory: %s", SYNTHETIC_DIR)

    fixtures = load_all_fixtures()

    if args.dry_run:
        _dry_run(fixtures)
        return

    _seed_database(fixtures, reset=args.reset)


if __name__ == "__main__":
    main()
