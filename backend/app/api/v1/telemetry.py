"""Telemetry endpoints (docs/05_API_SPEC.md).

Transport only: parse, delegate to `app.services.telemetry_service`, serialise.
No repository access, no SQL, and no quality rules — the classifier decides
every status and the service owns the transaction.

Exactly the four endpoints the API spec defines; no others.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.core.errors import NotFoundError, UrjaSetuError
from app.repositories import AggregatedReading
from app.schemas.common import ErrorResponse
from app.schemas.telemetry import (
    TelemetryBatchCreate,
    TelemetryBatchResult,
    TelemetryBucket,
    TelemetryIngestResult,
    TelemetryReadingCreate,
    TelemetryReadingRead,
    TelemetrySeriesRead,
)
from app.services import telemetry_service
from app.services.telemetry_service import IngestionOutcome

router = APIRouter(tags=["telemetry"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"}
}

# `90s`, `15m`, `1h`, `1d` — the shorthand a dashboard sends.
_DURATION = re.compile(r"^(?P<value>\d+)(?P<unit>[smhd])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# Window applied when the caller supplies no bounds.
DEFAULT_QUERY_WINDOW = timedelta(days=1)


class InvalidQueryParameterError(UrjaSetuError):
    """A query parameter is present but cannot be interpreted."""

    code = "INVALID_QUERY_PARAMETER"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


@router.post(
    "/telemetry/readings",
    response_model=TelemetryIngestResult,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest one normalized meter/asset reading",
    responses=NOT_FOUND,
)
def ingest_reading(payload: TelemetryReadingCreate, session: DbSession) -> TelemetryIngestResult:
    outcome = telemetry_service.ingest_reading(session, payload.to_normalized())
    return _to_ingest_result(outcome, payload)


@router.post(
    "/telemetry/readings/batch",
    response_model=TelemetryBatchResult,
    status_code=status.HTTP_201_CREATED,
    summary="Batch ingest readings",
    responses=NOT_FOUND,
)
def ingest_batch(payload: TelemetryBatchCreate, session: DbSession) -> TelemetryBatchResult:
    result = telemetry_service.ingest_batch(
        session, [item.to_normalized() for item in payload.readings]
    )
    return TelemetryBatchResult(
        submitted=result.total,
        ingested=result.stored,
        rejected=result.rejected,
        counts_by_status=result.counts_by_status(),
        readings=[
            _to_ingest_result(outcome, submitted)
            for outcome, submitted in zip(result.outcomes, payload.readings, strict=True)
        ],
    )


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@router.get(
    "/sites/{site_id}/telemetry",
    response_model=TelemetrySeriesRead,
    summary="Return normalized time-series",
    responses=NOT_FOUND,
)
def get_site_telemetry(
    site_id: UUID,
    session: DbSession,
    start: str | None = Query(default=None, description="ISO-8601 start of the window (inclusive)"),
    end: str | None = Query(default=None, description="ISO-8601 end of the window (exclusive)"),
    resolution: str | None = Query(
        default=None, description="Bucket size, e.g. `15m`, `1h`, or a number of seconds"
    ),
) -> TelemetrySeriesRead:
    """Readings whose interval starts within [start, end).

    Half-open so adjacent windows tile without double-counting the boundary
    reading. Without `resolution` the stored readings are returned, including
    ones flagged by quality — a time-series view has to show its gaps.
    """
    # Both bounds are optional: docs/05_API_SPEC.md lists them without marking
    # them required, and a caller browsing a site's recent data should not have
    # to compute a window. Defaults to the last day, ending now.
    window_end = _parse_timestamp(end, "end") if end else datetime.now(UTC)
    window_start = _parse_timestamp(start, "start") if start else window_end - DEFAULT_QUERY_WINDOW
    if window_end < window_start:
        raise InvalidQueryParameterError(
            "end must not precede start.", details={"start": start, "end": end}
        )
    bucket = _parse_duration(resolution) if resolution else None

    rows = telemetry_service.get_interval_for_site(
        session, site_id, start=window_start, end=window_end, resolution=bucket
    )

    if bucket is not None:
        buckets = [_to_bucket(row) for row in rows if isinstance(row, AggregatedReading)]
        return TelemetrySeriesRead(
            site_id=site_id,
            start=window_start,
            end=window_end,
            resolution_seconds=int(bucket.total_seconds()),
            count=len(buckets),
            readings=buckets,
        )

    readings = [TelemetryReadingRead.model_validate(row) for row in rows]
    return TelemetrySeriesRead(
        site_id=site_id,
        start=window_start,
        end=window_end,
        resolution_seconds=None,
        count=len(readings),
        readings=readings,
    )


@router.get(
    "/sites/{site_id}/telemetry/latest",
    response_model=TelemetryReadingRead,
    summary="Latest valid reading and quality metadata",
    responses=NOT_FOUND,
)
def get_latest_telemetry(site_id: UUID, session: DbSession) -> TelemetryReadingRead:
    """The most recent stored reading for a site, with its quality metadata.

    Not filtered by quality: a stale reading is still this site's latest
    telemetry, and the response says so via `quality_status`. 404 means the
    site has no telemetry at all, never that what it has has gone stale.
    """
    reading = telemetry_service.get_latest_for_site(session, site_id, only_valid=False)
    if reading is None:
        raise NotFoundError(
            "No valid telemetry recorded for this site.",
            code="TELEMETRY_NOT_FOUND",
            details={"site_id": str(site_id)},
        )
    return TelemetryReadingRead.model_validate(reading)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_ingest_result(
    outcome: IngestionOutcome, submitted: TelemetryReadingCreate
) -> TelemetryIngestResult:
    """Render an outcome, echoing what was submitted.

    The submitted values are echoed rather than read back from the row, because
    a rejected submission has no row to read.
    """
    normalized = submitted.to_normalized()
    return TelemetryIngestResult(
        id=outcome.reading.id if outcome.reading is not None else None,
        stored=outcome.stored,
        quality_status=outcome.quality_status,
        reason=outcome.assessment.reason,
        meter_id=normalized.meter_id,
        energy_asset_id=normalized.energy_asset_id,
        timestamp=normalized.timestamp,
        interval_start=normalized.interval_start,
        interval_end=normalized.interval_end,
        generation_kw=normalized.generation_kw,
        load_kw=normalized.load_kw,
        grid_import_kw=normalized.grid_import_kw,
        grid_export_kw=normalized.grid_export_kw,
        energy_kwh=normalized.energy_kwh,
        battery_soc=normalized.battery_soc,
        source=normalized.source,
    )


def _to_bucket(row: AggregatedReading) -> TelemetryBucket:
    return TelemetryBucket(
        timestamp=row.bucket_start,
        generation_kw=row.generation_kw,
        load_kw=row.load_kw,
        grid_import_kw=row.grid_import_kw,
        grid_export_kw=row.grid_export_kw,
        energy_kwh=row.energy_kwh,
        reading_count=row.reading_count,
    )


def _parse_timestamp(raw: str, field: str) -> datetime:
    """Parse an ISO-8601 timestamp from a query string.

    A literal `+` in a query string decodes to a space, so a correctly
    formatted `...T10:15:00+00:00` commonly arrives as `...T10:15:00 00:00`.
    ISO-8601 has no space in that position, so restoring it is unambiguous
    rather than a guess.
    """
    candidate = raw.strip()
    for attempt in (candidate, _restore_offset_sign(candidate)):
        if attempt is None:
            continue
        try:
            parsed = datetime.fromisoformat(attempt.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            raise InvalidQueryParameterError(
                f"{field} must include a timezone offset.", details={field: raw}
            )
        return parsed

    raise InvalidQueryParameterError(
        f"{field} is not a valid ISO-8601 timestamp.", details={field: raw}
    )


def _restore_offset_sign(value: str) -> str | None:
    """Turn a trailing ` HH:MM` offset back into `+HH:MM`."""
    head, sep, tail = value.rpartition(" ")
    if not sep or not re.fullmatch(r"\d{2}:\d{2}", tail):
        return None
    return f"{head}+{tail}"


def _parse_duration(raw: str) -> timedelta:
    """Parse `15m`, `1h`, `30s`, `1d`, or a bare number of seconds."""
    candidate = raw.strip()
    if match := _DURATION.fullmatch(candidate):
        seconds = int(match.group("value")) * _UNIT_SECONDS[match.group("unit")]
    elif candidate.isdigit():
        seconds = int(candidate)
    else:
        raise InvalidQueryParameterError(
            "resolution must be a duration such as `15m`, `1h`, or a number of seconds.",
            details={"resolution": raw},
        )

    if seconds <= 0:
        raise InvalidQueryParameterError(
            "resolution must be greater than zero.", details={"resolution": raw}
        )
    return timedelta(seconds=seconds)
