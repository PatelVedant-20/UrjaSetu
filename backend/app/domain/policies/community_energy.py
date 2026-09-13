"""Versioned synthetic Gujarat household profiles, not calibrated meter data.

15-minute interval averages, no battery. Solar declination varies by date;
clear-day envelope and household loads are explicit demonstration assumptions.
"""

import math
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
INTERVAL = timedelta(minutes=15)
VERSION = "gujarat-household-1"


def profile(
    moment: datetime,
    capacity: Decimal | float,
    consumer: bool = False,
    scenario: str = "normal",
    variant: int = 0,
) -> dict[str, Decimal]:
    local = (moment + INTERVAL / 2).astimezone(IST)
    hour = local.hour + local.minute / 60
    # Approximate astronomical daylight at Ahmedabad latitude; solar noon
    # near 12:40 IST. Clear-day seasonal output is synthetic, not weather data.
    declination = math.radians(
        23.44 * math.sin(2 * math.pi * (local.timetuple().tm_yday - 81) / 365)
    )
    lat = math.radians(23.0225)
    angle = math.radians(15 * (hour - 12.67))
    elevation = max(
        0,
        math.sin(lat) * math.sin(declination)
        + math.cos(lat) * math.cos(declination) * math.cos(angle),
    )
    solar = float(capacity) * elevation * 0.87
    load = (1.9 if consumer else 0.65) + 0.3 * math.sin(hour * 2 + variant) ** 2
    load += (1.2 if consumer else 0.65) * math.exp(-(((hour - 20) / 2) ** 2))
    load += 0.4 * math.exp(-(((hour - 8) / 1.5) ** 2))
    if scenario == "cloudy":
        solar *= 0.28
    if scenario == "congestion":
        load += 65
    gen, demand = (Decimal(str(round(v, 4))) for v in (solar, load))
    imp, exp = max(demand - gen, Decimal(0)), max(gen - demand, Decimal(0))
    return {
        "generation_kw": gen,
        "load_kw": demand,
        "grid_import_kw": imp,
        "grid_export_kw": exp,
        "generation_kwh": gen / 4,
        "load_kwh": demand / 4,
        "grid_import_kwh": imp / 4,
        "grid_export_kwh": exp / 4,
    }
