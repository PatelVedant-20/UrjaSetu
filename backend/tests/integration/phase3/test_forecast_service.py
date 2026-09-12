"""Phase 3 gate: telemetry -> forecast provider -> forecast_points -> surplus.

Exercises the orchestration layer against real PostgreSQL, using stand-in
providers. No forecasting algorithm is tested here — that is the provider's
own business, and the point of the boundary is that this layer cannot tell the
difference.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, UnprocessableError
from app.db.models import Meter, Site
from app.db.models.forecasting import ForecastRun
from app.domain.enums import ForecastRunStatus, ForecastType, TelemetrySource
from app.domain.interfaces.telemetry import NormalizedReading
from app.services import forecast_service, telemetry_service
from tests.integration.phase3.conftest import (
    NOW,
    FailingProvider,
    MisbehavingProvider,
    StubProvider,
)

HORIZON_START = NOW + timedelta(hours=1)
HORIZON_END = HORIZON_START + timedelta(hours=1)
INTERVAL = timedelta(minutes=15)


def _run(session: Session, site_id: uuid.UUID, provider: object, **kwargs: object):  # type: ignore[no-untyped-def]
    defaults: dict[str, object] = {
        "site_id": site_id,
        "forecast_type": ForecastType.SOLAR,
        "provider": provider,
        "horizon_start": HORIZON_START,
        "horizon_end": HORIZON_END,
        "interval": INTERVAL,
        "at": NOW,
    }
    return forecast_service.run_forecast(session, **{**defaults, **kwargs})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def test_run_persists_a_completed_run_and_its_points(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()
    provider = StubProvider()

    run = _run(db_session, site.id, provider)

    assert run.status is ForecastRunStatus.COMPLETED
    assert run.provider == "stub"
    assert run.model_version == "1.0.0"
    assert run.forecast_type is ForecastType.SOLAR
    points = forecast_service.get_points_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )
    assert len(points) == 4  # one hour at 15-minute resolution
    assert all(p.predicted_kw == Decimal("4.0000") for p in points)


def test_service_does_not_know_which_provider_it_called(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """Two unrelated providers drive the same orchestration unchanged.

    This is the replaceability guarantee: swapping the algorithm changes stored
    identifiers, never the code path.
    """
    site = make_site()

    baseline = _run(db_session, site.id, StubProvider(name="baseline", value=Decimal("2")))
    fancy = _run(
        db_session,
        site.id,
        StubProvider(name="gradient-boost", model_version="9.1", value=Decimal("7")),
    )

    assert baseline.provider == "baseline"
    assert fancy.provider == "gradient-boost"
    assert fancy.model_version == "9.1"
    assert baseline.status is fancy.status is ForecastRunStatus.COMPLETED


def test_provider_receives_the_requested_horizon_and_interval(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()
    provider = StubProvider()

    _run(db_session, site.id, provider)

    request = provider.calls[0]
    assert request.site_id == site.id
    assert request.horizon_start == HORIZON_START
    assert request.horizon_end == HORIZON_END
    assert request.interval == INTERVAL
    assert request.expected_point_count == 4


def test_generation_timestamp_is_distinct_from_prediction_intervals(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """`created_at` is when the forecast was made; intervals are when energy flows."""
    site = make_site()

    run = _run(db_session, site.id, StubProvider())

    assert run.created_at == NOW
    points = forecast_service.get_points_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )
    assert all(p.interval_start >= HORIZON_START for p in points)
    assert run.created_at < points[0].interval_start


def test_timestamps_are_timezone_aware(db_session: Session, make_site: Callable[..., Site]) -> None:
    site = make_site()
    run = _run(db_session, site.id, StubProvider())
    db_session.expire_all()
    stored = forecast_service.get_run(db_session, run.id)

    assert stored.horizon_start.tzinfo is not None
    assert stored.created_at.tzinfo is not None


def test_determinism_same_provider_same_input(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()

    first = _run(db_session, site.id, StubProvider())
    second = _run(db_session, site.id, StubProvider())

    a = forecast_service.get_run(db_session, first.id)
    b = forecast_service.get_run(db_session, second.id)
    points_a = forecast_service.get_points_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END, forecast_type=ForecastType.SOLAR
    )
    assert a.model_version == b.model_version
    # Both runs predicted the same values for the same intervals.
    assert len({p.predicted_kw for p in points_a}) == 1


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_unknown_site_is_rejected(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc:
        _run(db_session, uuid.uuid4(), StubProvider())

    assert exc.value.code == "SITE_NOT_FOUND"


def test_inverted_horizon_is_rejected(db_session: Session, make_site: Callable[..., Site]) -> None:
    site = make_site()

    with pytest.raises(UnprocessableError) as exc:
        _run(db_session, site.id, StubProvider(), horizon_end=HORIZON_START - timedelta(hours=1))

    assert exc.value.code == "FORECAST_HORIZON_INVALID"


def test_non_positive_interval_is_rejected(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()

    with pytest.raises(UnprocessableError) as exc:
        _run(db_session, site.id, StubProvider(), interval=timedelta(0))

    assert exc.value.code == "FORECAST_INTERVAL_INVALID"


def test_provider_that_does_not_support_the_type_is_refused(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """Refused before any run is recorded, rather than letting it improvise."""
    site = make_site()
    solar_only = StubProvider(supported=(ForecastType.SOLAR,))

    with pytest.raises(UnprocessableError) as exc:
        _run(db_session, site.id, solar_only, forecast_type=ForecastType.LOAD)

    assert exc.value.code == "FORECAST_TYPE_UNSUPPORTED"


# ---------------------------------------------------------------------------
# Provider failure and result validation
# ---------------------------------------------------------------------------


def test_provider_failure_is_recorded_not_swallowed(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """An adapter failure must stay observable (docs/01_FINAL_ARCHITECTURE.md)."""
    site = make_site()

    with pytest.raises(UnprocessableError) as exc:
        _run(db_session, site.id, FailingProvider())

    assert exc.value.code == "FORECAST_PROVIDER_FAILED"
    # The attempt survives the failure, with the reason attached.
    failed = db_session.query(ForecastRun).filter_by(status=ForecastRunStatus.FAILED).all()
    assert failed, "a failed provider must still leave a run row"
    assert "RuntimeError" in (failed[-1].error or "")
    assert failed[-1].provider == "stub"


@pytest.mark.parametrize(
    "mode",
    ["empty", "outside_horizon", "duplicate_interval", "inverted_interval", "bad_confidence"],
)
def test_contract_violations_are_rejected(
    db_session: Session, make_site: Callable[..., Site], mode: str
) -> None:
    """A provider's output is checked at the boundary, never assumed."""
    site = make_site()

    with pytest.raises(UnprocessableError):
        _run(db_session, site.id, MisbehavingProvider(mode=mode))


def test_wrong_forecast_type_returned_is_rejected(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()

    with pytest.raises(UnprocessableError):
        _run(db_session, site.id, MisbehavingProvider(mode="wrong_type"))


def test_no_points_are_stored_for_a_failed_run(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()

    with pytest.raises(UnprocessableError):
        _run(db_session, site.id, FailingProvider())

    assert (
        forecast_service.get_points_for_site(
            db_session, site.id, start=HORIZON_START, end=HORIZON_END
        )
        == []
    )


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_get_run_reports_status(db_session: Session, make_site: Callable[..., Site]) -> None:
    site = make_site()
    run = _run(db_session, site.id, StubProvider())

    assert forecast_service.get_run(db_session, run.id).status is ForecastRunStatus.COMPLETED


def test_get_run_rejects_unknown_id(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc:
        forecast_service.get_run(db_session, uuid.uuid4())

    assert exc.value.code == "FORECAST_RUN_NOT_FOUND"


def test_points_from_incomplete_runs_are_not_returned(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """Only a completed run is a forecast anyone should act on."""
    site = make_site()

    with pytest.raises(UnprocessableError):
        _run(db_session, site.id, FailingProvider())

    assert (
        forecast_service.get_points_for_site(
            db_session, site.id, start=HORIZON_START, end=HORIZON_END
        )
        == []
    )


def test_points_are_scoped_to_the_site(db_session: Session, make_site: Callable[..., Site]) -> None:
    mine = make_site()
    theirs = make_site()
    _run(db_session, mine.id, StubProvider(value=Decimal("3")))
    _run(db_session, theirs.id, StubProvider(value=Decimal("9")))

    points = forecast_service.get_points_for_site(
        db_session, mine.id, start=HORIZON_START, end=HORIZON_END
    )

    assert points
    assert all(p.site_id == mine.id for p in points)
    assert all(p.predicted_kw == Decimal("3.0000") for p in points)


# ---------------------------------------------------------------------------
# Telemetry -> forecasting integration
# ---------------------------------------------------------------------------


def test_provider_receives_site_telemetry_as_history(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
) -> None:
    """The gate's first arrow: telemetry reaches the provider."""
    site = make_site()
    meter = make_meter(site_id=site.id)
    for offset in (3, 2, 1):
        start = NOW - INTERVAL * offset
        telemetry_service.ingest_reading(
            db_session,
            NormalizedReading(
                meter_id=meter.id,
                timestamp=start + INTERVAL,
                interval_start=start,
                interval_end=start + INTERVAL,
                source=TelemetrySource.METER,
                generation_kw=Decimal("2.0"),
                load_kw=Decimal("1.0"),
            ),
            at=NOW,
            staleness_threshold=timedelta(hours=2),
        )
    provider = StubProvider()

    _run(db_session, site.id, provider, horizon_start=NOW, horizon_end=NOW + timedelta(hours=1))

    history = provider.calls[0].history
    assert len(history) == 3
    assert all(h.generation_kw == Decimal("2.0000") for h in history)
    # Oldest first.
    assert [h.interval_start for h in history] == sorted(h.interval_start for h in history)


def test_history_sums_meters_across_a_site(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
) -> None:
    """A forecast is about the site, not about one meter."""
    site = make_site()
    start = NOW - INTERVAL
    for _ in range(2):
        meter = make_meter(site_id=site.id)
        telemetry_service.ingest_reading(
            db_session,
            NormalizedReading(
                meter_id=meter.id,
                timestamp=start + INTERVAL,
                interval_start=start,
                interval_end=start + INTERVAL,
                source=TelemetrySource.METER,
                generation_kw=Decimal("2.0"),
            ),
            at=NOW,
            staleness_threshold=timedelta(hours=2),
        )
    provider = StubProvider()

    _run(db_session, site.id, provider, horizon_start=NOW, horizon_end=NOW + timedelta(hours=1))

    history = provider.calls[0].history
    assert len(history) == 1
    assert history[0].generation_kw == Decimal("4.0000")


def test_unusable_telemetry_is_not_fed_to_a_provider(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
) -> None:
    """Fitting to data the platform distrusts would launder it into a forecast."""
    site = make_site()
    meter = make_meter(site_id=site.id)
    start = NOW - INTERVAL
    telemetry_service.ingest_reading(
        db_session,
        NormalizedReading(
            meter_id=meter.id,
            timestamp=start + INTERVAL,
            interval_start=start,
            interval_end=start + INTERVAL,
            source=TelemetrySource.METER,
            generation_kw=Decimal("2.0"),
            source_unavailable=True,
        ),
        at=NOW,
    )
    provider = StubProvider()

    _run(db_session, site.id, provider, horizon_start=NOW, horizon_end=NOW + timedelta(hours=1))

    assert provider.calls[0].history == ()


def test_site_with_no_telemetry_still_reaches_the_provider(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """Whether a cold-start site can be forecast is the provider's decision."""
    site = make_site()
    provider = StubProvider()

    run = _run(db_session, site.id, provider)

    assert provider.calls[0].history == ()
    assert run.status is ForecastRunStatus.COMPLETED


# ---------------------------------------------------------------------------
# Surplus
# ---------------------------------------------------------------------------


def test_surplus_pairs_the_solar_and_load_forecasts(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """The gate's last arrow: forecast_points -> surplus."""
    site = make_site()
    _run(db_session, site.id, StubProvider(value=Decimal("5")), forecast_type=ForecastType.SOLAR)
    _run(db_session, site.id, StubProvider(value=Decimal("2")), forecast_type=ForecastType.LOAD)

    window = forecast_service.get_surplus_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )

    assert len(window.points) == 4
    assert all(p.surplus_kw == Decimal("3.0000") for p in window.points)
    # 3 kW across four quarter-hours = 3 kWh
    assert window.total_exportable_kwh == Decimal("3")


def test_surplus_uses_the_newest_forecast_for_an_interval(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """Re-forecasting must not double-count a site's energy."""
    site = make_site()
    _run(
        db_session,
        site.id,
        StubProvider(value=Decimal("5")),
        forecast_type=ForecastType.SOLAR,
        at=NOW - timedelta(hours=2),
    )
    _run(
        db_session,
        site.id,
        StubProvider(value=Decimal("8")),
        forecast_type=ForecastType.SOLAR,
        at=NOW,
    )
    _run(db_session, site.id, StubProvider(value=Decimal("1")), forecast_type=ForecastType.LOAD)

    window = forecast_service.get_surplus_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )

    assert len(window.points) == 4
    assert all(p.surplus_kw == Decimal("7.0000") for p in window.points)


def test_surplus_without_a_load_forecast_is_unknown(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()
    _run(db_session, site.id, StubProvider(value=Decimal("5")), forecast_type=ForecastType.SOLAR)

    window = forecast_service.get_surplus_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )

    assert all(p.surplus_kw is None for p in window.points)
    assert window.total_exportable_kwh == Decimal("0")


def test_surplus_for_a_site_with_no_forecasts_is_empty(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    site = make_site()

    window = forecast_service.get_surplus_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )

    assert window.points == []


def test_surplus_rejects_unknown_site(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc:
        forecast_service.get_surplus_for_site(
            db_session, uuid.uuid4(), start=HORIZON_START, end=HORIZON_END
        )

    assert exc.value.code == "SITE_NOT_FOUND"


def test_full_phase_3_gate(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
) -> None:
    """telemetry -> forecast provider -> forecast_points -> surplus."""
    site = make_site()
    meter = make_meter(site_id=site.id)
    for offset in (2, 1):
        start = NOW - INTERVAL * offset
        telemetry_service.ingest_reading(
            db_session,
            NormalizedReading(
                meter_id=meter.id,
                timestamp=start + INTERVAL,
                interval_start=start,
                interval_end=start + INTERVAL,
                source=TelemetrySource.METER,
                generation_kw=Decimal("6.0"),
                load_kw=Decimal("1.5"),
            ),
            at=NOW,
            staleness_threshold=timedelta(hours=2),
        )

    solar_provider = StubProvider(name="baseline", value=Decimal("6"))
    load_provider = StubProvider(name="baseline", value=Decimal("1.5"))
    solar_run = _run(db_session, site.id, solar_provider, forecast_type=ForecastType.SOLAR)
    _run(db_session, site.id, load_provider, forecast_type=ForecastType.LOAD)

    assert solar_provider.calls[0].history, "telemetry must reach the provider"
    assert solar_run.status is ForecastRunStatus.COMPLETED

    points = forecast_service.get_points_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )
    assert len(points) == 8  # solar + load, four buckets each

    window = forecast_service.get_surplus_for_site(
        db_session, site.id, start=HORIZON_START, end=HORIZON_END
    )
    assert all(p.surplus_kw == Decimal("4.5000") for p in window.points)
    assert window.has_exportable_energy is True
