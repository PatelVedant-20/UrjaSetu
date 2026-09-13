"""Phase 2: telemetry persistence.

Proves `telemetry_readings` stores normalized measurements in PostgreSQL with
the constraints, indexes and timezone behaviour the data model requires, and
that integrity is enforced by the database rather than only in Python.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Meter, Site, TelemetryReading
from app.domain.enums import TelemetryQualityStatus, TelemetrySource

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
INTERVAL = timedelta(minutes=15)


def _row(meter_id: uuid.UUID, **overrides: object) -> TelemetryReading:
    interval_start = overrides.pop("interval_start", NOW - INTERVAL)
    defaults: dict[str, object] = {
        "meter_id": meter_id,
        "timestamp": NOW,
        "interval_start": interval_start,
        "interval_end": interval_start + INTERVAL,  # type: ignore[operator]
        "generation_kw": Decimal("3.5000"),
        "energy_kwh": Decimal("0.8750"),
        "quality_status": TelemetryQualityStatus.VALID,
        "source": TelemetrySource.METER,
    }
    return TelemetryReading(**{**defaults, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_table_exists(engine) -> None:  # type: ignore[no-untyped-def]
    assert "telemetry_readings" in set(inspect(engine).get_table_names())


def test_expected_columns(engine) -> None:  # type: ignore[no-untyped-def]
    """Exactly the fields of docs/04_DATA_MODEL.md entity 10, plus shared ones."""
    columns = {c["name"] for c in inspect(engine).get_columns("telemetry_readings")}

    assert columns == {
        "id",
        "meter_id",
        "energy_asset_id",
        "timestamp",
        "interval_start",
        "interval_end",
        "generation_kw",
        "load_kw",
        "grid_import_kw",
        "grid_export_kw",
        "energy_kwh",
        "generation_kwh",
        "load_kwh",
        "grid_import_kwh",
        "grid_export_kwh",
        "battery_soc",
        "quality_status",
        "source",
        "created_at",
        "updated_at",
    }


def test_meter_timestamp_indexes_exist(engine) -> None:  # type: ignore[no-untyped-def]
    """docs/04_DATA_MODEL.md requires a (meter, timestamp)-style index."""
    names = {i["name"] for i in inspect(engine).get_indexes("telemetry_readings")}

    assert "ix_telemetry_readings_meter_id_interval_start" in names
    assert "ix_telemetry_readings_meter_id_timestamp" in names


# ---------------------------------------------------------------------------
# Persistence and timezone handling
# ---------------------------------------------------------------------------


def test_store_and_read_back(db_session: Session, make_meter: Callable[..., Meter]) -> None:
    meter = make_meter()
    reading = _row(meter.id)
    db_session.add(reading)
    db_session.flush()

    stored = db_session.get(TelemetryReading, reading.id)

    assert stored is not None
    assert isinstance(stored.id, uuid.UUID)
    assert stored.generation_kw == Decimal("3.5000")
    assert isinstance(stored.generation_kw, Decimal)
    assert stored.quality_status is TelemetryQualityStatus.VALID
    assert stored.source is TelemetrySource.METER


def test_timestamps_are_timezone_aware_utc(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    """docs/00_PROJECT_BIBLE.md section 6: UTC in storage."""
    meter = make_meter()
    reading = _row(meter.id)
    db_session.add(reading)
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(TelemetryReading, reading.id)

    assert stored is not None
    for value in (stored.timestamp, stored.interval_start, stored.interval_end):
        assert value.tzinfo is not None
    assert stored.interval_end - stored.interval_start == INTERVAL
    # Ingestion metadata is distinct from measurement time.
    assert stored.created_at.tzinfo is not None


def test_non_utc_input_is_stored_as_the_same_instant(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    """An offset-aware timestamp keeps its instant, not its wall-clock reading.

    India Standard Time is the realistic case (docs/11_REGULATORY_AND_INDIA_CONTEXT.md):
    17:30 IST and 12:00 UTC are the same moment, and storage must agree.
    """
    ist = timezone(timedelta(hours=5, minutes=30))
    same_instant_ist = datetime(2026, 6, 1, 17, 30, tzinfo=ist)
    meter = make_meter()
    reading = _row(meter.id, timestamp=same_instant_ist)
    db_session.add(reading)
    db_session.flush()
    db_session.expire_all()

    stored = db_session.get(TelemetryReading, reading.id)

    assert stored is not None
    assert stored.timestamp == same_instant_ist
    assert stored.timestamp == datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_null_measurement_is_distinct_from_zero(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    """NULL means "not measured"; 0 means "measured, and it was zero"."""
    meter = make_meter()
    unmeasured = _row(meter.id, generation_kw=None, energy_kwh=None, load_kw=None)
    measured_zero = _row(
        meter.id,
        interval_start=NOW - 2 * INTERVAL,
        generation_kw=Decimal("0"),
        energy_kwh=Decimal("0"),
    )
    db_session.add_all([unmeasured, measured_zero])
    db_session.flush()

    assert unmeasured.generation_kw is None
    assert measured_zero.generation_kw == Decimal("0")


def test_optional_asset_scope(
    db_session: Session,
    make_meter: Callable[..., Meter],
    make_energy_asset: Callable[..., object],
    make_site: Callable[..., Site],
) -> None:
    site = make_site()
    meter = make_meter(site_id=site.id)
    asset = make_energy_asset(site_id=site.id)

    site_level = _row(meter.id)
    asset_level = _row(meter.id, energy_asset_id=asset.id)  # type: ignore[attr-defined]
    db_session.add_all([site_level, asset_level])
    db_session.flush()

    assert site_level.energy_asset_id is None
    assert asset_level.energy_asset_id == asset.id  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------


def test_duplicate_interval_is_rejected_by_the_database(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    """The natural key stops the same interval being recorded twice."""
    meter = make_meter()
    db_session.add(_row(meter.id))
    db_session.flush()

    db_session.add(_row(meter.id))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_null_asset_ids_are_not_treated_as_distinct(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    """NULLS NOT DISTINCT: two whole-site readings cannot share an interval.

    Without it PostgreSQL treats each NULL as unique and the same interval could
    be inserted repeatedly, double-counting energy at settlement.
    """
    meter = make_meter()
    db_session.add(_row(meter.id, energy_asset_id=None))
    db_session.flush()

    db_session.add(_row(meter.id, energy_asset_id=None))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_interval_allowed_for_different_assets(
    db_session: Session,
    make_site: Callable[..., Site],
    make_meter: Callable[..., Meter],
    make_energy_asset: Callable[..., object],
) -> None:
    """Separate channels on one meter are separate series."""
    site = make_site()
    meter = make_meter(site_id=site.id)
    first = make_energy_asset(site_id=site.id)
    second = make_energy_asset(site_id=site.id)

    db_session.add_all(
        [
            _row(meter.id, energy_asset_id=first.id),  # type: ignore[attr-defined]
            _row(meter.id, energy_asset_id=second.id),  # type: ignore[attr-defined]
        ]
    )
    db_session.flush()


def test_interval_end_before_start_is_rejected(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    meter = make_meter()
    db_session.add(_row(meter.id, interval_start=NOW, interval_end=NOW - INTERVAL))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_zero_length_interval_is_allowed(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    """An instantaneous sample is a zero-length interval."""
    meter = make_meter()
    db_session.add(_row(meter.id, interval_start=NOW, interval_end=NOW))
    db_session.flush()


@pytest.mark.parametrize(
    "column", ["generation_kw", "load_kw", "grid_import_kw", "grid_export_kw", "energy_kwh"]
)
def test_negative_measurements_are_rejected(
    db_session: Session, make_meter: Callable[..., Meter], column: str
) -> None:
    meter = make_meter()
    db_session.add(_row(meter.id, **{column: Decimal("-0.0001")}))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_battery_soc_outside_percent_range_is_rejected(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    meter = make_meter()
    db_session.add(_row(meter.id, battery_soc=Decimal("100.01")))

    with pytest.raises((IntegrityError, DataError)):
        db_session.flush()


def test_reading_requires_an_existing_meter(db_session: Session) -> None:
    db_session.add(_row(uuid.uuid4()))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_meter_cascades_to_its_readings(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    meter = make_meter()
    db_session.add(_row(meter.id))
    db_session.flush()

    db_session.execute(text("DELETE FROM meters WHERE id = :mid"), {"mid": meter.id})
    db_session.flush()

    remaining = db_session.execute(
        text("SELECT count(*) FROM telemetry_readings WHERE meter_id = :mid"), {"mid": meter.id}
    ).scalar_one()
    assert remaining == 0


def test_quality_status_persists_as_lowercase_value(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    meter = make_meter()
    reading = _row(meter.id, quality_status=TelemetryQualityStatus.OUT_OF_ORDER)
    db_session.add(reading)
    db_session.flush()

    row = db_session.execute(
        text("SELECT quality_status::text, source::text FROM telemetry_readings WHERE id = :rid"),
        {"rid": reading.id},
    ).one()

    assert row == ("out_of_order", "meter")


def test_unknown_quality_status_is_rejected_by_the_database(
    db_session: Session, make_meter: Callable[..., Meter]
) -> None:
    meter = make_meter()
    reading = _row(meter.id)
    db_session.add(reading)
    db_session.flush()

    with pytest.raises((IntegrityError, DataError)):
        db_session.execute(
            text("UPDATE telemetry_readings SET quality_status = 'suspicious' WHERE id = :rid"),
            {"rid": reading.id},
        )
