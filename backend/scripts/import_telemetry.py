#!/usr/bin/env python3
"""import_telemetry.py — Telemetry Ingestion and Simulation Importer for UrjaSetu.

PURPOSE:
--------
CLI tool to parse, validate, and normalize telemetry from CSV files or synthetic
profiles for development, testing, and demonstration.

USAGE:
------
    # 1. Preview parsing of a CSV file without database connection (dry run):
    python backend/scripts/import_telemetry.py --csv path/to/meter_data.csv --dry-run

    # 2. Generate synthetic prosumer telemetry and export normalized JSON:
    python backend/scripts/import_telemetry.py --synthetic --days 2 --output-json telemetry.json

    # 3. Import CSV with a fallback meter UUID:
    python backend/scripts/import_telemetry.py --csv data.csv --meter-id 1000... --dry-run

SAFETY:
-------
- Fails safely if APP_ENV is 'production'.
- Deterministic simulation using explicit random seeds.
- Does not modify database models or bypass domain services.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

# Add backend directory to sys.path if running directly as script
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.meter import (  # noqa: E402
    AdapterError,
    MeterSimulatorAdapter,
    NormalizedTelemetryBatch,
    make_deterministic_uuid,
)
from app.core.config import get_settings  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.domain.interfaces.telemetry import NormalizedReading  # noqa: E402
from app.services import telemetry_service  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("import_telemetry")


def _json_serial(obj: Any) -> Any:
    """JSON serializer for Decimal, UUID, and datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")


def run_importer(
    csv_path: Path | None = None,
    synthetic: bool = False,
    meter_id: UUID | None = None,
    site_id: UUID | None = None,
    asset_id: UUID | None = None,
    days: int = 1,
    interval_minutes: int = 15,
    seed: int = 42,
    batch_size: int = 100,
    strict: bool = True,
    dry_run: bool = True,
    output_json: Path | None = None,
) -> NormalizedTelemetryBatch:
    """Execute the telemetry importer workflow."""
    settings = get_settings()
    if settings.app_env == "production":
        raise PermissionError(
            "Telemetry importer is not permitted to run in production environment."
        )

    logger.info("Starting telemetry import (env=%s, dry_run=%s)", settings.app_env, dry_run)

    adapter = MeterSimulatorAdapter(
        default_meter_id=meter_id,
        default_site_id=site_id,
        default_energy_asset_id=asset_id,
        seed=seed,
    )

    batch: NormalizedTelemetryBatch

    if csv_path:
        logger.info("Reading CSV file: %s (strict=%s)", csv_path, strict)
        batch = adapter.load_from_csv_file(csv_path, strict=strict)
    elif synthetic:
        logger.info(
            "Generating synthetic telemetry: days=%d, interval=%d min, seed=%d",
            days,
            interval_minutes,
            seed,
        )
        now = datetime.now(UTC)
        start_time = datetime(now.year, now.month, now.day, 0, 0, tzinfo=UTC)
        end_time = start_time + timedelta(days=days)
        target_meter = meter_id or make_deterministic_uuid("meter", 1)

        batch = adapter.generate_synthetic(
            meter_id=target_meter,
            site_id=site_id,
            # Left unset when the caller names no asset. docs/04_DATA_MODEL.md
            # makes energy_asset_id nullable because a whole-site meter reading
            # is not attributable to one asset; fabricating an id here produced
            # readings that referenced an asset which does not exist.
            energy_asset_id=asset_id,
            start_time=start_time,
            end_time=end_time,
            interval_minutes=interval_minutes,
        )
    else:
        raise ValueError("Must specify either --csv <path> or --synthetic")

    logger.info(
        "Successfully normalized %d readings from source '%s'",
        len(batch.readings),
        batch.source_name,
    )

    if batch.errors:
        logger.warning("Encountered %d row validation errors during parsing:", len(batch.errors))
        for err in batch.errors[:10]:
            logger.warning("  - %s", err)
        if len(batch.errors) > 10:
            logger.warning("  ... and %d more errors", len(batch.errors) - 10)

    # Optional JSON export
    if output_json:
        logger.info("Exporting normalized readings to: %s", output_json)
        data = [asdict(r) for r in batch.readings]
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(data, f, default=_json_serial, indent=2)
        logger.info("Export complete.")

    # In dry-run mode, compute summary stats
    if dry_run:
        total_gen = sum(r.generation_kw for r in batch.readings)
        total_load = sum(r.load_kw for r in batch.readings)
        total_import = sum(r.grid_import_kw for r in batch.readings)
        total_export = sum(r.grid_export_kw for r in batch.readings)
        logger.info("=== Telemetry Ingestion Summary (Dry Run) ===")
        logger.info("Total Readings:    %d", len(batch.readings))
        logger.info("Total Generation:  %s kW (sum)", total_gen)
        logger.info("Total Demand/Load: %s kW (sum)", total_load)
        logger.info("Total Grid Import: %s kW (sum)", total_import)
        logger.info("Total Grid Export: %s kW (sum)", total_export)
        logger.info(
            "Batch streaming test: %d batches of size %d",
            math.ceil(len(batch.readings) / batch_size) if batch.readings else 0,
            batch_size,
        )
    else:
        _dispatch_to_service(batch.readings, batch_size=batch_size)

    return batch


def _dispatch_to_service(readings: list[NormalizedReading], *, batch_size: int) -> None:
    """Hand normalized readings to the telemetry service.

    The importer's whole job ends at producing `NormalizedReading` values. The
    service owns quality classification, duplicate handling, batching and
    persistence, so nothing here writes to PostgreSQL directly and no
    ingestion rule is duplicated (docs/03_REPOSITORY_STRUCTURE.md).

    Each chunk is one service call and therefore one transaction, so a failure
    part-way through leaves earlier chunks committed and the current one
    untouched, rather than half-writing a chunk.
    """
    if not readings:
        logger.warning("Nothing to ingest: the adapter produced no readings.")
        return

    totals: Counter[str] = Counter()
    stored = 0

    with session_scope() as session:
        for chunk in MeterSimulatorAdapter.stream_batches(readings, batch_size=batch_size):
            result = telemetry_service.ingest_batch(session, chunk)
            stored += result.stored
            for status, count in result.counts_by_status().items():
                totals[status.value] += count

    logger.info("=== Telemetry Ingestion Summary (Live) ===")
    logger.info("Submitted:  %d", len(readings))
    logger.info("Stored:     %d", stored)
    logger.info("Rejected:   %d", len(readings) - stored)
    for status, count in sorted(totals.items()):
        logger.info("  %-20s %d", status, count)


def main() -> None:
    """Parse command line arguments and run the importer."""
    parser = argparse.ArgumentParser(
        description="UrjaSetu Telemetry Importer and Simulator",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv", type=Path, help="Path to input CSV file")
    group.add_argument("--synthetic", action="store_true", help="Generate synthetic telemetry")

    parser.add_argument("--meter-id", type=UUID, default=None, help="Meter UUID")
    parser.add_argument("--site-id", type=UUID, default=None, help="Site UUID")
    parser.add_argument("--asset-id", type=UUID, default=None, help="Energy Asset UUID")
    parser.add_argument("--days", type=int, default=1, help="Days of synthetic data (default: 1)")
    parser.add_argument(
        "--interval", type=int, default=15, help="Interval in minutes (default: 15)"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for determinism (default: 42)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Batch chunk size (default: 100)"
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Skip invalid rows instead of aborting",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Run in dry-run mode (default)",
    )
    parser.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Run in live ingestion mode instead of dry-run",
    )
    parser.add_argument(
        "--output-json", type=Path, default=None, help="Path to export normalized JSON"
    )

    parser.set_defaults(strict=True, dry_run=True)
    args = parser.parse_args()

    try:
        run_importer(
            csv_path=args.csv,
            synthetic=args.synthetic,
            meter_id=args.meter_id,
            site_id=args.site_id,
            asset_id=args.asset_id,
            days=args.days,
            interval_minutes=args.interval,
            seed=args.seed,
            batch_size=args.batch_size,
            strict=args.strict,
            dry_run=args.dry_run,
            output_json=args.output_json,
        )
    except (AdapterError, ValueError, FileNotFoundError) as e:
        logger.error("Telemetry import failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
