"""Unit tests for MeterSimulatorAdapter and SyntheticTelemetryGenerator."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.adapters.meter import (
    MeterSimulatorAdapter,
    NormalizedTelemetryReading,
    SyntheticTelemetryGenerator,
    make_deterministic_uuid,
)

SAMPLE_METER_ID = UUID("10000000-0000-0000-0000-000000000001")
SAMPLE_SITE_ID = UUID("20000000-0000-0000-0000-000000000001")
SAMPLE_ASSET_ID = UUID("30000000-0000-0000-0000-000000000001")


def test_deterministic_uuid_generation() -> None:
    uuid1 = make_deterministic_uuid("meter", 1)
    uuid2 = make_deterministic_uuid("meter", 1)
    uuid3 = make_deterministic_uuid("meter", 2)

    assert uuid1 == uuid2
    assert uuid1 != uuid3
    assert isinstance(uuid1, UUID)


def test_synthetic_telemetry_generation_determinism() -> None:
    gen1 = SyntheticTelemetryGenerator(seed=12345)
    gen2 = SyntheticTelemetryGenerator(seed=12345)

    start = datetime(2026, 9, 12, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 13, 0, 0, 0, tzinfo=UTC)

    readings1 = gen1.generate_site_telemetry(
        meter_id=SAMPLE_METER_ID,
        site_id=SAMPLE_SITE_ID,
        energy_asset_id=SAMPLE_ASSET_ID,
        start_time=start,
        end_time=end,
        interval_minutes=15,
        profile_type="residential_prosumer",
    )

    readings2 = gen2.generate_site_telemetry(
        meter_id=SAMPLE_METER_ID,
        site_id=SAMPLE_SITE_ID,
        energy_asset_id=SAMPLE_ASSET_ID,
        start_time=start,
        end_time=end,
        interval_minutes=15,
        profile_type="residential_prosumer",
    )

    # 24 hours * 4 readings/hour = 96 readings
    assert len(readings1) == 96
    assert len(readings2) == 96

    for r1, r2 in zip(readings1, readings2, strict=True):
        assert r1.timestamp == r2.timestamp
        assert r1.generation_kw == r2.generation_kw
        assert r1.load_kw == r2.load_kw
        assert r1.grid_import_kw == r2.grid_import_kw
        assert r1.grid_export_kw == r2.grid_export_kw
        assert r1.voltage_pu == r2.voltage_pu


def test_synthetic_solar_diurnal_curve_physics() -> None:
    gen = SyntheticTelemetryGenerator(seed=42)
    start = datetime(2026, 9, 12, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 13, 0, 0, 0, tzinfo=UTC)

    readings = gen.generate_site_telemetry(
        meter_id=SAMPLE_METER_ID,
        energy_asset_id=SAMPLE_ASSET_ID,
        start_time=start,
        end_time=end,
        pv_capacity_kw=Decimal("6.0"),
    )

    # Nighttime readings (e.g. 02:00 UTC) must have 0 solar generation
    night_readings = [r for r in readings if r.timestamp.hour in (1, 2, 3, 23, 0)]
    for r in night_readings:
        assert r.generation_kw == Decimal("0.0")

    # Midday readings (around 12:00 - 13:00) must have significant solar generation
    midday_readings = [r for r in readings if r.timestamp.hour in (11, 12, 13)]
    for r in midday_readings:
        assert r.generation_kw > Decimal("2.0")


def test_synthetic_consumer_without_asset() -> None:
    gen = SyntheticTelemetryGenerator(seed=42)
    start = datetime(2026, 9, 12, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 13, 0, 0, 0, tzinfo=UTC)

    readings = gen.generate_site_telemetry(
        meter_id=SAMPLE_METER_ID,
        energy_asset_id=None,  # Pure consumer, no PV asset
        start_time=start,
        end_time=end,
        profile_type="residential_consumer",
    )

    assert len(readings) == 96
    for r in readings:
        assert r.generation_kw == Decimal("0.0")
        assert r.grid_export_kw == Decimal("0.0")
        assert r.grid_import_kw == r.load_kw


def test_meter_simulator_adapter_facade() -> None:
    adapter = MeterSimulatorAdapter(
        default_meter_id=SAMPLE_METER_ID,
        default_site_id=SAMPLE_SITE_ID,
        seed=99,
    )

    batch = adapter.generate_synthetic(
        start_time=datetime(2026, 9, 12, 0, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 9, 12, 6, 0, 0, tzinfo=UTC),
        interval_minutes=15,
    )

    assert len(batch.readings) == 24
    assert batch.source_name == "synthetic_simulator"


def test_batch_streaming_chunks() -> None:
    readings = [
        NormalizedTelemetryReading(
            meter_id=SAMPLE_METER_ID,
            timestamp=datetime(2026, 9, 12, 10, i, 0, tzinfo=UTC),
            interval_start=datetime(2026, 9, 12, 10, i, 0, tzinfo=UTC),
            interval_end=datetime(2026, 9, 12, 10, i + 15, 0, tzinfo=UTC),
            generation_kw=Decimal("3.0"),
            load_kw=Decimal("1.0"),
            grid_import_kw=Decimal("0.0"),
            grid_export_kw=Decimal("2.0"),
        )
        for i in range(10)
    ]

    chunks = list(MeterSimulatorAdapter.stream_batches(readings, batch_size=3))
    assert len(chunks) == 4
    assert len(chunks[0]) == 3
    assert len(chunks[1]) == 3
    assert len(chunks[2]) == 3
    assert len(chunks[3]) == 1
