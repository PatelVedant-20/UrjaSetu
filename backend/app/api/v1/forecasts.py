"""Forecasting endpoints (docs/05_API_SPEC.md).

Transport only: parse, delegate to `app.services.forecast_service`, serialise.
No repository access, no persistence, and no forecasting — the router never
learns which algorithm ran. Provider selection happens in the service via the
registry, which is what docs/05_API_SPEC.md means by "selected via
configuration/domain policy, not hard-coded in routers".

Exactly the four endpoints the API spec defines; no others.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession
from app.core.errors import UrjaSetuError
from app.domain.enums import ForecastType
from app.schemas.common import ErrorResponse
from app.schemas.forecasts import (
    ForecastPointRead,
    ForecastRunCreate,
    ForecastRunRead,
    ForecastSeriesRead,
    SurplusPointRead,
    SurplusRead,
)
from app.services import forecast_service

router = APIRouter(tags=["forecasting"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Resource not found"}
}
UNPROCESSABLE: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "Provider or request could not be processed"}
}

# Window applied when a caller supplies no bounds: the day ahead, which is the
# market mode this platform runs (docs/00_PROJECT_BIBLE.md section 7).
DEFAULT_QUERY_WINDOW = timedelta(days=1)

# Declared once so both query endpoints describe the window identically.
StartQuery = Annotated[str | None, Query(description="ISO-8601 start of the window")]
EndQuery = Annotated[str | None, Query(description="ISO-8601 end of the window")]


class InvalidQueryParameterError(UrjaSetuError):
    """A query parameter is present but cannot be interpreted."""

    code = "INVALID_QUERY_PARAMETER"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


@router.post(
    "/forecasts/runs",
    response_model=ForecastRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a forecast run using the configured provider",
    responses={**NOT_FOUND, **UNPROCESSABLE},
)
def create_forecast_run(payload: ForecastRunCreate, session: DbSession) -> ForecastRunRead:
    """Run a forecast and persist its points.

    `provider` is optional: omitted, the configured default is used. The router
    passes the name through without resolving it, so no implementation is named
    at this layer.
    """
    run = forecast_service.run_forecast(
        session,
        site_id=payload.site_id,
        forecast_type=payload.forecast_type,
        provider=payload.provider,
        horizon_start=payload.horizon_start,
        horizon_end=payload.horizon_end,
        interval=payload.to_interval(),
    )
    return ForecastRunRead.model_validate(run)


@router.get(
    "/forecasts/runs/{run_id}",
    response_model=ForecastRunRead,
    summary="Forecast run status",
    responses=NOT_FOUND,
)
def get_forecast_run(run_id: UUID, session: DbSession) -> ForecastRunRead:
    return ForecastRunRead.model_validate(forecast_service.get_run(session, run_id))


@router.get(
    "/sites/{site_id}/forecasts",
    response_model=ForecastSeriesRead,
    summary="Return forecast points",
    responses=NOT_FOUND,
)
def get_site_forecasts(
    site_id: UUID,
    session: DbSession,
    start: StartQuery = None,
    end: EndQuery = None,
    forecast_type: Annotated[
        ForecastType | None, Query(description="Restrict to one forecast type")
    ] = None,
) -> ForecastSeriesRead:
    """Points from completed runs whose interval starts within the window."""
    window_start, window_end = _window(start, end)
    points = forecast_service.get_points_for_site(
        session, site_id, start=window_start, end=window_end, forecast_type=forecast_type
    )
    return ForecastSeriesRead(
        site_id=site_id,
        start=window_start,
        end=window_end,
        count=len(points),
        points=[ForecastPointRead.model_validate(p) for p in points],
    )


@router.get(
    "/sites/{site_id}/surplus",
    response_model=SurplusRead,
    summary="Return estimated available surplus for a window",
    responses=NOT_FOUND,
)
def get_site_surplus(
    site_id: UUID,
    session: DbSession,
    start: StartQuery = None,
    end: EndQuery = None,
) -> SurplusRead:
    """Expected surplus, derived from the newest solar and load forecasts.

    The arithmetic lives in `app.domain.policies.surplus`; this endpoint only
    projects the result.
    """
    window_start, window_end = _window(start, end)
    surplus = forecast_service.get_surplus_for_site(
        session, site_id, start=window_start, end=window_end
    )
    return SurplusRead(
        site_id=site_id,
        start=window_start,
        end=window_end,
        total_exportable_kwh=surplus.total_exportable_kwh,
        has_exportable_energy=surplus.has_exportable_energy,
        points=[
            SurplusPointRead(
                interval_start=p.interval_start,
                interval_end=p.interval_end,
                generation_kw=p.generation_kw,
                load_kw=p.load_kw,
                surplus_kw=p.surplus_kw,
                exportable_kw=p.exportable_kw,
            )
            for p in surplus.points
        ],
    )


def _window(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    """Resolve the query window, defaulting to the day ahead.

    Both bounds are optional: docs/05_API_SPEC.md lists them without marking
    them required, and a caller asking "what is this site expected to do?"
    should not have to compute a horizon.
    """
    window_start = _parse_timestamp(start, "start") if start else datetime.now(UTC)
    window_end = _parse_timestamp(end, "end") if end else window_start + DEFAULT_QUERY_WINDOW
    if window_end < window_start:
        raise InvalidQueryParameterError(
            "end must not precede start.", details={"start": start, "end": end}
        )
    return window_start, window_end


def _parse_timestamp(raw: str, field: str) -> datetime:
    """Parse an ISO-8601 timestamp from a query string.

    A literal `+` in a query string decodes to a space, so a correctly
    formatted offset commonly arrives as `...T10:15:00 00:00`. ISO-8601 has no
    space in that position, so restoring it is unambiguous rather than a guess.
    """
    candidate = raw.strip()
    attempts = [candidate]
    head, sep, tail = candidate.rpartition(" ")
    if sep and len(tail) == 5 and tail[2] == ":":
        attempts.append(f"{head}+{tail}")

    for attempt in attempts:
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
