"""Forecast persistence queries.

Query construction only — no orchestration and no algorithm
(docs/03_REPOSITORY_STRUCTURE.md). Never commits: the caller owns the
transaction boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models.forecasting import ForecastPoint, ForecastRun
from app.domain.enums import ForecastRunStatus, ForecastType
from app.repositories.base import BaseRepository


class ForecastRunRepository(BaseRepository[ForecastRun]):
    model = ForecastRun

    def get_with_points(self, run_id: UUID) -> ForecastRun | None:
        """Load a run together with its points in one round trip."""
        stmt = (
            select(ForecastRun)
            .where(ForecastRun.id == run_id)
            .options(selectinload(ForecastRun.points))
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def latest_completed_for_site(
        self,
        site_id: UUID,
        forecast_type: ForecastType,
        *,
        covering: datetime | None = None,
    ) -> ForecastRun | None:
        """Most recent completed run of a type that produced points for a site.

        "Most recent" is by `created_at` — when the forecast was *made* — not
        by horizon. Re-forecasting the same window is normal, and the newest
        prediction is the one that should be used.

        `covering` narrows to runs whose horizon contains that instant, so a
        caller asking about a specific time does not get a stale horizon that
        happens to be the newest run.
        """
        stmt = (
            select(ForecastRun)
            .join(ForecastPoint, ForecastPoint.forecast_run_id == ForecastRun.id)
            .where(
                ForecastPoint.site_id == site_id,
                ForecastRun.forecast_type == forecast_type,
                ForecastRun.status == ForecastRunStatus.COMPLETED,
            )
        )
        if covering is not None:
            stmt = stmt.where(
                ForecastRun.horizon_start <= covering, ForecastRun.horizon_end > covering
            )
        stmt = stmt.order_by(ForecastRun.created_at.desc()).limit(1)
        return self.session.execute(stmt).scalars().first()


class ForecastPointRepository(BaseRepository[ForecastPoint]):
    model = ForecastPoint

    def add_all(self, points: Sequence[ForecastPoint]) -> Sequence[ForecastPoint]:
        """Stage many points and flush once.

        A forecast horizon is written as a unit; a per-row round trip would
        dominate the cost of a run.
        """
        self.session.add_all(points)
        self.session.flush()
        return points

    def list_for_run(self, forecast_run_id: UUID) -> Sequence[ForecastPoint]:
        stmt = (
            select(ForecastPoint)
            .where(ForecastPoint.forecast_run_id == forecast_run_id)
            .order_by(ForecastPoint.interval_start.asc())
        )
        return self.session.execute(stmt).scalars().all()

    def list_for_site(
        self,
        site_id: UUID,
        *,
        start: datetime,
        end: datetime,
        forecast_type: ForecastType | None = None,
        forecast_run_id: UUID | None = None,
    ) -> Sequence[ForecastPoint]:
        """Points whose interval starts within [start, end).

        Half-open so adjacent horizons tile without predicting the boundary
        bucket twice. Only points from completed runs are returned: a pending
        or failed run's rows are not a forecast anyone should act on.
        """
        stmt = (
            select(ForecastPoint)
            .join(ForecastRun, ForecastRun.id == ForecastPoint.forecast_run_id)
            .where(
                ForecastPoint.site_id == site_id,
                ForecastPoint.interval_start >= start,
                ForecastPoint.interval_start < end,
                ForecastRun.status == ForecastRunStatus.COMPLETED,
            )
        )
        if forecast_type is not None:
            stmt = stmt.where(ForecastRun.forecast_type == forecast_type)
        if forecast_run_id is not None:
            stmt = stmt.where(ForecastPoint.forecast_run_id == forecast_run_id)

        # Newest run last, so a caller keeping the final value per interval
        # naturally keeps the most recent prediction for it.
        stmt = stmt.order_by(ForecastPoint.interval_start.asc(), ForecastRun.created_at.asc())
        return self.session.execute(stmt).scalars().all()

    def latest_per_interval_for_site(
        self,
        site_id: UUID,
        *,
        start: datetime,
        end: datetime,
        forecast_type: ForecastType,
    ) -> Sequence[ForecastPoint]:
        """One point per interval — the most recently generated prediction.

        A site is normally forecast repeatedly over overlapping horizons, so a
        raw window query returns several predictions for the same bucket.
        Surplus needs exactly one per interval, or the same energy would be
        counted once per run that predicted it.
        """
        newest: dict[datetime, ForecastPoint] = {}
        for point in self.list_for_site(site_id, start=start, end=end, forecast_type=forecast_type):
            newest[point.interval_start] = point
        return [newest[key] for key in sorted(newest)]
