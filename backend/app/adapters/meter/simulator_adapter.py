"""Meter Simulator and Synthetic Telemetry Generator for UrjaSetu.

Provides:
1. `SyntheticTelemetryGenerator`: Deterministic, physics-aligned synthetic generation
   and load time-series profiles calibrated to Indian feeder conditions (Gujarat context).
2. `MeterSimulatorAdapter`: Unified facade supporting CSV loading, synthetic generation,
   and batch streaming to downstream services.

DETERMINISM & SAFETY:
- All synthetic generation uses an explicit seed (default=42).
- Zero external API dependencies, zero real customer IDs or credentials.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_DNS, UUID, uuid5
from zoneinfo import ZoneInfo

from app.adapters.meter.contracts import (
    NormalizedReading,
    NormalizedTelemetryBatch,
)
from app.adapters.meter.csv_adapter import TelemetryCSVAdapter
from app.domain.enums import TelemetrySource

# Fixed deterministic namespace for synthetic mock UUID generation
_SYNTHETIC_UUID_NAMESPACE = NAMESPACE_DNS


def make_deterministic_uuid(entity_type: str, index: int) -> UUID:
    """Generate a reproducible, clearly synthetic UUID for development/testing."""
    return uuid5(_SYNTHETIC_UUID_NAMESPACE, f"urjasetu.synthetic.{entity_type}.{index}")


class SyntheticTelemetryGenerator:
    """Deterministic synthetic telemetry time-series generator.

    Generates realistic 15-minute interval energy telemetry incorporating:
    - Physical solar irradiance curves (diurnal cycle, solar noon peak, seasonal scaling)
    - Realistic Indian residential/commercial load patterns (morning & evening peaks)
    - Deterministic stochastic variations controlled by random seed
    - Physical grid balance (import/export calculated from load - gen).
    """

    def __init__(self, seed: int = 42) -> None:
        """Initialize generator with a fixed random seed."""
        self.seed = seed

    def generate_site_telemetry(
        self,
        meter_id: UUID,
        site_id: UUID | None = None,
        energy_asset_id: UUID | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        interval_minutes: int = 15,
        profile_type: Literal[
            "residential_prosumer", "residential_consumer", "commercial"
        ] = "residential_prosumer",
        pv_capacity_kw: Decimal = Decimal("5.0"),
        base_load_kw: Decimal = Decimal("1.2"),
        peak_load_kw: Decimal = Decimal("4.5"),
    ) -> list[NormalizedReading]:
        """Generate a deterministic sequence of normalized telemetry readings.

        Args:
            meter_id: The UUID of the reporting meter.
            site_id: The optional UUID of the prosumer/consumer site.
            energy_asset_id: The optional UUID of the PV asset (None if consumer only).
            start_time: Start datetime in UTC (default: today 00:00 UTC).
            end_time: End datetime in UTC (default: start_time + 24 hours).
            interval_minutes: Time-step duration in minutes (default: 15).
            profile_type: Type of consumer/prosumer profile.
            pv_capacity_kw: Rated solar capacity in kW.
            base_load_kw: Minimum off-peak base load in kW.
            peak_load_kw: Maximum peak load in kW.

        Returns:
            List of `NormalizedReading` objects conforming to domain contracts.
        """
        # Set up time window in UTC
        if start_time is None:
            now_utc = datetime.now(UTC)
            start_time = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, tzinfo=UTC)
        elif start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UTC)
        else:
            start_time = start_time.astimezone(UTC)

        if end_time is None:
            end_time = start_time + timedelta(days=1)
        elif end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=UTC)
        else:
            end_time = end_time.astimezone(UTC)

        # Initialize local deterministic PRNG
        rng = random.Random(self.seed + int(start_time.timestamp()))

        readings: list[NormalizedReading] = []
        current_time = start_time
        delta = timedelta(minutes=interval_minutes)

        while current_time < end_time:
            interval_start = current_time
            interval_end = current_time + delta

            # Decimal hours into the day (0.0 to 24.0)
            local_time = current_time.astimezone(ZoneInfo("Asia/Kolkata"))
            hour_of_day = local_time.hour + local_time.minute / 60.0

            # 1. Solar Generation Model (half-sine curve between 06:00 and 18:00)
            gen_kw = Decimal("0.0")
            if (
                profile_type in ("residential_prosumer", "commercial")
                and energy_asset_id is not None
                and 6.0 <= hour_of_day <= 18.0
            ):
                # Solar angle: 0 at 6am, pi at 6pm, peak at 12pm
                solar_angle = (hour_of_day - 6.0) / 12.0 * math.pi
                ideal_ratio = math.sin(solar_angle)
                # Add mild deterministic weather fluctuation (-10% to +5%)
                weather_factor = 0.90 + (rng.random() * 0.15)
                gen_val = float(pv_capacity_kw) * ideal_ratio * weather_factor
                gen_kw = Decimal(str(round(max(0.0, gen_val), 3)))

            # 2. Demand / Load Model (Indian residential/commercial diurnal curve)
            load_factor = self._compute_load_factor(hour_of_day, profile_type, rng)
            load_val = float(base_load_kw) + (float(peak_load_kw - base_load_kw) * load_factor)
            load_kw = Decimal(str(round(max(0.1, load_val), 3)))

            # 3. Grid Import / Export Balance
            net_kw = load_kw - gen_kw
            if net_kw >= Decimal("0.0"):
                grid_import_kw = net_kw
                grid_export_kw = Decimal("0.0")
            else:
                grid_import_kw = Decimal("0.0")
                grid_export_kw = abs(net_kw)

            # 4. Energy (kWh) = Power (kW) * (interval_minutes / 60.0)
            hours_ratio = Decimal(str(interval_minutes / 60.0))
            energy_kwh = (load_kw * hours_ratio).quantize(Decimal("0.001"))

            # Voltage is deliberately not simulated here: it is a grid quantity
            # (docs/04_DATA_MODEL.md entity 16, `grid_snapshots`) belonging to
            # the Phase 6 digital twin, not a telemetry reading channel.

            # 6. Battery SoC if applicable
            battery_soc = None
            if profile_type == "commercial":
                # Simulated battery cycle: discharge at peaks, charge during solar noon
                if 10.0 <= hour_of_day <= 15.0:
                    battery_soc = Decimal("85.0")
                elif 18.0 <= hour_of_day <= 22.0:
                    battery_soc = Decimal("35.0")
                else:
                    battery_soc = Decimal("60.0")

            reading = NormalizedReading(
                meter_id=meter_id,
                energy_asset_id=energy_asset_id,
                timestamp=current_time,
                interval_start=interval_start,
                interval_end=interval_end,
                generation_kw=gen_kw,
                load_kw=load_kw,
                grid_import_kw=grid_import_kw,
                grid_export_kw=grid_export_kw,
                energy_kwh=energy_kwh,
                battery_soc=battery_soc,
                source=TelemetrySource.SIMULATOR,
            )
            readings.append(reading)
            current_time += delta

        return readings

    def _compute_load_factor(
        self,
        hour: float,
        profile_type: str,
        rng: random.Random,
    ) -> float:
        """Calculate load proportion (0.0 to 1.0) based on time of day and profile."""
        noise = (rng.random() - 0.5) * 0.10

        if profile_type == "commercial":
            # Business hours load profile: high between 9am and 7pm
            if 9.0 <= hour <= 19.0:
                base = 0.85
            elif 7.0 <= hour < 9.0 or 19.0 < hour <= 21.0:
                base = 0.40
            else:
                base = 0.15
        else:
            # Residential Indian profile: Morning peak (7am-10am), evening peak (6pm-10pm)
            if 6.5 <= hour <= 10.0:
                # Morning peak
                progress = (hour - 6.5) / 3.5
                base = 0.40 + 0.50 * math.sin(progress * math.pi)
            elif 17.5 <= hour <= 22.5:
                # Evening peak (highest demand)
                progress = (hour - 17.5) / 5.0
                base = 0.50 + 0.50 * math.sin(progress * math.pi)
            elif 10.0 < hour < 17.5:
                # Afternoon lull
                base = 0.35
            else:
                # Night base
                base = 0.10

        return max(0.0, min(1.0, base + noise))


class MeterSimulatorAdapter:
    """Unified telemetry simulator adapter supporting CSV and synthetic sources."""

    def __init__(
        self,
        default_meter_id: UUID | None = None,
        default_site_id: UUID | None = None,
        default_energy_asset_id: UUID | None = None,
        seed: int = 42,
    ) -> None:
        self.default_meter_id = default_meter_id
        self.default_site_id = default_site_id
        self.default_energy_asset_id = default_energy_asset_id
        self.csv_adapter = TelemetryCSVAdapter(
            default_meter_id=default_meter_id,
            default_site_id=default_site_id,
            default_energy_asset_id=default_energy_asset_id,
            source_name="meter_simulator",
        )
        self.synthetic_generator = SyntheticTelemetryGenerator(seed=seed)
        # Populated by generate_synthetic / load_from_csv_*; replayed by read().
        self._last_batch = NormalizedTelemetryBatch(source_name="meter_simulator")

    def read(self, *, since: datetime | None = None) -> list[NormalizedReading]:
        """Yield normalized readings, oldest first.

        Satisfies `app.domain.interfaces.telemetry.MeterReadingSource`, so the
        telemetry service can consume the simulator exactly as it would consume
        a real meter. Replays whatever the most recent `generate_synthetic` or
        `load_from_csv_*` call produced.
        """
        readings = sorted(self._last_batch.readings, key=lambda r: r.interval_start)
        if since is not None:
            readings = [r for r in readings if r.interval_start >= since]
        return readings

    def load_from_csv_file(
        self, file_path: str | Path, strict: bool = True
    ) -> NormalizedTelemetryBatch:
        """Parse and normalize telemetry data from a CSV file."""
        self.csv_adapter.strict = strict
        self._last_batch = self.csv_adapter.parse_file(file_path)
        return self._last_batch

    def load_from_csv_string(self, content: str, strict: bool = True) -> NormalizedTelemetryBatch:
        """Parse and normalize telemetry data from raw CSV text."""
        self.csv_adapter.strict = strict
        self._last_batch = self.csv_adapter.parse_string(content)
        return self._last_batch

    def generate_synthetic(
        self,
        meter_id: UUID | None = None,
        site_id: UUID | None = None,
        energy_asset_id: UUID | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        interval_minutes: int = 15,
        profile_type: Literal[
            "residential_prosumer", "residential_consumer", "commercial"
        ] = "residential_prosumer",
        pv_capacity_kw: Decimal = Decimal("5.0"),
    ) -> NormalizedTelemetryBatch:
        """Generate a batch of normalized synthetic readings."""
        target_meter = meter_id or self.default_meter_id or make_deterministic_uuid("meter", 1)
        target_site = site_id or self.default_site_id
        target_asset = energy_asset_id or self.default_energy_asset_id

        readings = self.synthetic_generator.generate_site_telemetry(
            meter_id=target_meter,
            site_id=target_site,
            energy_asset_id=target_asset,
            start_time=start_time,
            end_time=end_time,
            interval_minutes=interval_minutes,
            profile_type=profile_type,
            pv_capacity_kw=pv_capacity_kw,
        )

        self._last_batch = NormalizedTelemetryBatch(
            source_name="synthetic_simulator",
            readings=readings,
            total_records=len(readings),
            errors=[],
        )
        return self._last_batch

    @staticmethod
    def stream_batches(
        readings: list[NormalizedReading],
        batch_size: int = 100,
    ) -> Iterator[list[NormalizedReading]]:
        """Yield chunks/batches of normalized readings for streaming ingestion."""
        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got: {batch_size}")
        for i in range(0, len(readings), batch_size):
            yield readings[i : i + batch_size]
