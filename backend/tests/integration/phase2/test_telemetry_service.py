"""Phase 2 acceptance gate: ingest -> store -> query latest -> query interval -> quality status.

Exercises the service the telemetry API will call, against real PostgreSQL.
The API itself is another agent's file and is not touched here.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.models import Meter, Site
from app.domain.enums import TelemetryQualityStatus, TelemetrySource
from app.repositories import AggregatedReading
from app.services import telemetry_service

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Ingest -> store
# ---------------------------------------------------------------------------


def test_ingest_single_reading(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    meter = make_meter()

    outcome = telemetry_service.ingest_reading(db_session, make_reading(meter.id), at=NOW)

    assert outcome.quality_status is TelemetryQualityStatus.VALID
    assert outcome.stored is True
    assert outcome.reading is not None
    assert outcome.reading.meter_id == meter.id
    assert outcome.reading.source is TelemetrySource.SIMULATOR


def test_ingest_rejects_unknown_meter(
    db_session: Session, make_reading: Callable[..., object]
) -> None:
    with pytest.raises(NotFoundError) as exc:
        telemetry_service.ingest_reading(db_session, make_reading(uuid.uuid4()), at=NOW)

    assert exc.value.code == "METER_NOT_FOUND"


def test_ingest_rejects_unknown_asset(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    meter = make_meter()

    with pytest.raises(NotFoundError) as exc:
        telemetry_service.ingest_reading(
            db_session, make_reading(meter.id, energy_asset_id=uuid.uuid4()), at=NOW
        )

    assert exc.value.code == "ENERGY_ASSET_NOT_FOUND"


def test_ingest_batch_stores_every_reading(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    meter = make_meter()
    readings = [make_reading(meter.id, interval_start=NOW - INTERVAL * (4 - i)) for i in range(4)]

    result = telemetry_service.ingest_batch(
        db_session, readings, at=NOW, staleness_threshold=timedelta(hours=2)
    )

    assert result.total == 4
    assert result.stored == 4
    assert result.accepted == 4
    assert result.flagged == 0


# ---------------------------------------------------------------------------
# Quality status through the service
# ---------------------------------------------------------------------------


def test_duplicate_is_reported_and_not_stored_twice(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    """Re-submitting an interval must never double-count energy."""
    meter = make_meter()
    reading = make_reading(meter.id)
    telemetry_service.ingest_reading(db_session, reading, at=NOW)

    second = telemetry_service.ingest_reading(db_session, reading, at=NOW)

    assert second.quality_status is TelemetryQualityStatus.DUPLICATE
    assert second.stored is False
    summary = telemetry_service.get_quality_summary(db_session, meter.site_id)
    assert summary[TelemetryQualityStatus.VALID] == 1


def test_duplicate_within_one_batch_is_detected(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    """A batch containing the same interval twice behaves like two calls."""
    meter = make_meter()
    reading = make_reading(meter.id)

    result = telemetry_service.ingest_batch(db_session, [reading, reading], at=NOW)

    assert result.counts_by_status() == {
        TelemetryQualityStatus.VALID: 1,
        TelemetryQualityStatus.DUPLICATE: 1,
    }
    assert result.stored == 1


def test_out_of_order_reading_is_flagged_and_kept(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    """Late data is recorded, not discarded — the gap must stay visible."""
    meter = make_meter()
    telemetry_service.ingest_reading(db_session, make_reading(meter.id), at=NOW)

    late = telemetry_service.ingest_reading(
        db_session, make_reading(meter.id, interval_start=NOW - INTERVAL * 4), at=NOW
    )

    assert late.quality_status is TelemetryQualityStatus.OUT_OF_ORDER
    assert late.stored is True


def test_stale_reading_is_flagged(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    meter = make_meter()

    outcome = telemetry_service.ingest_reading(
        db_session, make_reading(meter.id, interval_start=NOW - timedelta(days=1)), at=NOW
    )

    assert outcome.quality_status is TelemetryQualityStatus.STALE
    assert outcome.stored is True


def test_missing_reading_is_recorded_as_a_gap(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    meter = make_meter()

    outcome = telemetry_service.ingest_reading(
        db_session,
        make_reading(
            meter.id,
            generation_kw=None,
            load_kw=None,
            grid_import_kw=None,
            grid_export_kw=None,
            energy_kwh=None,
        ),
        at=NOW,
    )

    assert outcome.quality_status is TelemetryQualityStatus.MISSING
    assert outcome.stored is True


def test_invalid_value_is_flagged_not_crashed(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    """A bad value is classified before it can hit a CHECK constraint."""
    meter = make_meter()

    outcome = telemetry_service.ingest_reading(
        db_session, make_reading(meter.id, battery_soc=Decimal("150")), at=NOW
    )

    assert outcome.quality_status is TelemetryQualityStatus.INVALID_VALUE
    # Not written: it would fail the battery_soc CHECK constraint and take the
    # whole ingestion down with it.
    assert outcome.stored is False
    assert telemetry_service.get_quality_summary(db_session, meter.site_id) == {}


def test_source_unavailable_is_recorded(
    db_session: Session, make_meter: Callable[..., Meter], make_reading: Callable[..., object]
) -> None:
    """docs/00_PROJECT_BIBLE.md: a missing source must not break the platform."""
    meter = make_meter()

    outcome = telemetry_service.ingest_reading(
        db_session, make_reading(meter.id, source_unavailable=True), at=NOW
    )

    assert outcome.quality_status is TelemetryQualityStatus.SOURCE_UNAVAILABLE
    assert outcome.stored is True


# ---------------------------------------------------------------------------
# Query latest
# ---------------------------------------------------------------------------


def test_latest_returns_the_most_recent_valid_reading(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    site = make_site()
    meter = make_meter(site_id=site.id)
    for offset in (4, 3, 2, 1):
        telemetry_service.ingest_reading(
            db_session, make_reading(meter.id, interval_start=NOW - INTERVAL * offset), at=NOW
        )

    latest = telemetry_service.get_latest_for_site(db_session, site.id)

    assert latest is not None
    assert latest.interval_start == NOW - INTERVAL
    assert latest.quality_status is TelemetryQualityStatus.VALID


def test_latest_skips_unusable_readings(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    """`only_valid=True` selects the last-known-valid reading.

    The default returns the latest stored reading instead, so a site whose
    newest reading is unusable still reports telemetry — with the status that
    says so.
    """
    site = make_site()
    meter = make_meter(site_id=site.id)
    telemetry_service.ingest_reading(
        db_session, make_reading(meter.id, interval_start=NOW - INTERVAL * 2), at=NOW
    )
    # A newer reading that is stored but unusable: last-known-valid must skip
    # it and fall back to the older valid one.
    telemetry_service.ingest_reading(
        db_session,
        make_reading(meter.id, interval_start=NOW - INTERVAL, source_unavailable=True),
        at=NOW,
    )

    # Default: the latest *stored* reading, whatever its quality. Recency must
    # never make a site's telemetry disappear.
    latest = telemetry_service.get_latest_for_site(db_session, site.id)
    # Opt in for the last-known-*valid* fallback of
    # docs/01_FINAL_ARCHITECTURE.md's stale-telemetry path.
    latest_valid = telemetry_service.get_latest_for_site(db_session, site.id, only_valid=True)

    assert latest is not None
    assert latest.interval_start == NOW - INTERVAL
    assert latest.quality_status is TelemetryQualityStatus.SOURCE_UNAVAILABLE
    assert latest_valid is not None
    assert latest_valid.interval_start == NOW - INTERVAL * 2
    assert latest_valid.quality_status is TelemetryQualityStatus.VALID


def test_latest_on_an_empty_series_is_none(
    db_session: Session, make_site: Callable[..., Site]
) -> None:
    """An empty series is a normal state, not an error."""
    site = make_site()

    assert telemetry_service.get_latest_for_site(db_session, site.id) is None


def test_latest_rejects_unknown_site(db_session: Session) -> None:
    with pytest.raises(NotFoundError) as exc:
        telemetry_service.get_latest_for_site(db_session, uuid.uuid4())

    assert exc.value.code == "SITE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Query interval
# ---------------------------------------------------------------------------


def test_interval_query_returns_readings_in_order(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    site = make_site()
    meter = make_meter(site_id=site.id)
    for offset in range(1, 5):
        telemetry_service.ingest_reading(
            db_session, make_reading(meter.id, interval_start=NOW - INTERVAL * offset), at=NOW
        )

    rows = telemetry_service.get_interval_for_site(
        db_session, site.id, start=NOW - INTERVAL * 4, end=NOW
    )

    assert len(rows) == 4
    starts = [r.interval_start for r in rows]  # type: ignore[union-attr]
    assert starts == sorted(starts)


def test_interval_window_is_closed_on_timestamp(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    """The public window is [start, end] on `timestamp`, inclusive both ends.

    A caller naming two readings by their timestamps gets both of them back.
    """
    site = make_site()
    meter = make_meter(site_id=site.id)
    for offset in (2, 1):
        telemetry_service.ingest_reading(
            db_session, make_reading(meter.id, interval_start=NOW - INTERVAL * offset), at=NOW
        )
    # Timestamps are interval_end: NOW - INTERVAL and NOW.
    rows = telemetry_service.get_interval_for_site(
        db_session, site.id, start=NOW - INTERVAL, end=NOW
    )

    assert len(rows) == 2
    assert rows[0].timestamp == NOW - INTERVAL  # type: ignore[union-attr]
    assert rows[-1].timestamp == NOW  # type: ignore[union-attr]

    # Naming only the earlier timestamp returns only that reading.
    narrow = telemetry_service.get_interval_for_site(
        db_session, site.id, start=NOW - INTERVAL, end=NOW - INTERVAL
    )
    assert len(narrow) == 1


def test_interval_query_is_scoped_to_the_site(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    """Site scoping goes through meters.site_id, as the data model specifies."""
    mine = make_site()
    theirs = make_site()
    my_meter = make_meter(site_id=mine.id)
    their_meter = make_meter(site_id=theirs.id)
    telemetry_service.ingest_reading(db_session, make_reading(my_meter.id), at=NOW)
    telemetry_service.ingest_reading(db_session, make_reading(their_meter.id), at=NOW)

    rows = telemetry_service.get_interval_for_site(
        db_session, mine.id, start=NOW - INTERVAL * 4, end=NOW
    )

    assert len(rows) == 1
    assert rows[0].meter_id == my_meter.id  # type: ignore[union-attr]


def test_interval_query_with_resolution_aggregates(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    """`resolution` from docs/05_API_SPEC.md resamples into fixed buckets."""
    site = make_site()
    meter = make_meter(site_id=site.id)
    start = NOW - INTERVAL * 4
    for offset in range(4):
        telemetry_service.ingest_reading(
            db_session,
            make_reading(
                meter.id,
                interval_start=start + INTERVAL * offset,
                generation_kw=Decimal("2.0000"),
                energy_kwh=Decimal("0.5000"),
            ),
            at=NOW,
            staleness_threshold=timedelta(hours=2),
        )

    buckets = telemetry_service.get_interval_for_site(
        db_session, site.id, start=start, end=NOW, resolution=timedelta(minutes=30)
    )

    # Buckets are binned on `timestamp` over the closed window [start, NOW].
    # The four readings report at start+15, +30, +45 and +60, so 30-minute
    # buckets anchored at `start` hold 1, 2 and 1 reading respectively.
    assert len(buckets) == 3
    assert all(isinstance(b, AggregatedReading) for b in buckets)
    assert [b.reading_count for b in buckets] == [1, 2, 1]
    # Power averages, energy sums — the only combination that preserves units.
    middle = buckets[1]
    assert middle.generation_kw == Decimal("2.0000")
    assert middle.energy_kwh == Decimal("1.0000")


def test_aggregation_excludes_unusable_readings(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    """Averaging a stale reading into a summary would launder it into truth."""
    site = make_site()
    meter = make_meter(site_id=site.id)
    start = NOW - INTERVAL * 2
    telemetry_service.ingest_reading(
        db_session,
        make_reading(meter.id, interval_start=start, generation_kw=Decimal("2.0000")),
        at=NOW,
    )
    telemetry_service.ingest_reading(
        db_session,
        make_reading(meter.id, interval_start=start + INTERVAL, generation_kw=Decimal("100.0000")),
        # Evaluated far in the future, so this one lands as stale.
        at=NOW + timedelta(days=1),
    )

    buckets = telemetry_service.get_interval_for_site(
        db_session, site.id, start=start, end=NOW, resolution=timedelta(minutes=30)
    )

    assert len(buckets) == 1
    assert buckets[0].generation_kw == Decimal("2.0000")
    assert buckets[0].reading_count == 1


# ---------------------------------------------------------------------------
# Quality status summary
# ---------------------------------------------------------------------------


def test_quality_summary_counts_every_state(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    site = make_site()
    meter = make_meter(site_id=site.id)
    telemetry_service.ingest_reading(
        db_session, make_reading(meter.id, interval_start=NOW - INTERVAL), at=NOW
    )
    telemetry_service.ingest_reading(
        db_session,
        make_reading(meter.id, interval_start=NOW - INTERVAL * 2, source_unavailable=True),
        at=NOW,
    )
    # Arrives behind the series, so out_of_order outranks stale.
    telemetry_service.ingest_reading(
        db_session, make_reading(meter.id, interval_start=NOW - timedelta(days=2)), at=NOW
    )

    summary = telemetry_service.get_quality_summary(db_session, site.id)

    assert summary[TelemetryQualityStatus.VALID] == 1
    assert summary[TelemetryQualityStatus.SOURCE_UNAVAILABLE] == 1
    assert summary[TelemetryQualityStatus.OUT_OF_ORDER] == 1


def test_full_phase_2_gate(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_reading: Callable[..., object],
) -> None:
    """ingest -> store -> query latest -> query interval -> quality status."""
    site = make_site()
    meter = make_meter(site_id=site.id)

    result = telemetry_service.ingest_batch(
        db_session,
        [make_reading(meter.id, interval_start=NOW - INTERVAL * (4 - i)) for i in range(4)],
        at=NOW,
        staleness_threshold=timedelta(hours=2),
    )
    assert result.stored == 4

    latest = telemetry_service.get_latest_for_site(db_session, site.id)
    assert latest is not None
    assert latest.interval_start == NOW - INTERVAL

    window = telemetry_service.get_interval_for_site(
        db_session, site.id, start=NOW - INTERVAL * 4, end=NOW
    )
    assert len(window) == 4

    summary = telemetry_service.get_quality_summary(db_session, site.id)
    assert summary == {TelemetryQualityStatus.VALID: 4}
