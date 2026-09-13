"""Deterministic, profile-based household model. Never a utility measurement.

The monthly input calibrates mean daily demand (30 days); occupancy, appliances
and presence distribute it through the day. Solar uses a daylight envelope,
orientation/tilt derating and a 0.82 performance ratio. These are configurable
engineering assumptions, not a Gujarat tariff or a calibrated PV forecast.
"""

import hashlib
import math
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any

from app.domain.policies.community_energy import IST

VERSION = "gujarat-personal-2"
CITIES = {
    "Ahmedabad": (23.0225, 72.5714),
    "Surat": (21.1702, 72.8311),
    "Vadodara": (22.3072, 73.1812),
    "Rajkot": (22.3039, 70.8022),
    "Gandhinagar": (23.2156, 72.6369),
}
DEFAULTS: dict[str, Any] = {
    "city": "Ahmedabad",
    "home_type": "independent",
    "occupants": 4,
    "monthly_kwh": 360,
    "ac_count": 1,
    "has_ev": False,
    "daytime_home": True,
    "orientation": "south",
    "tilt": 23,
    "retail_rate": 7.0,
    "share_stats": True,
}


def shape(hour: float, occupants: int, ac: int, ev: bool, home: bool) -> float:
    base = 0.28 + occupants * 0.045
    morning = (0.55 + occupants * 0.07) * math.exp(-(((hour - 7.8) / 1.5) ** 2))
    evening = (0.8 + occupants * 0.08) * math.exp(-(((hour - 20) / 2.0) ** 2))
    cooling = ac * (
        0.42 * math.exp(-(((hour - 15) / 3.0) ** 2)) + 0.32 * math.exp(-(((hour - 23) / 2.0) ** 2))
    )
    presence = 0.35 * math.exp(-(((hour - 13) / 3.0) ** 2)) if home else 0
    charging = 1.6 * math.exp(-(((hour - 22) / 1.2) ** 2)) if ev else 0
    return base + morning + evening + cooling + presence + charging


@lru_cache(maxsize=1024)
def normalization(occupants: int, ac: int, ev: bool, home: bool) -> float:
    return sum(shape((i + 0.5) / 4, occupants, ac, ev, home) / 4 for i in range(96))


def power(
    moment: datetime, capacity: float, settings: dict[str, Any], seed: str
) -> dict[str, float]:
    p = DEFAULTS | settings
    local = moment.astimezone(IST)
    hour = local.hour + local.minute / 60 + local.second / 3600
    phase = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF * math.tau
    day = local.timetuple().tm_yday
    args = (int(p["occupants"]), int(p["ac_count"]), bool(p["has_ev"]), bool(p["daytime_home"]))
    load = float(p["monthly_kwh"]) / 30 * shape(hour, *args) / normalization(*args)
    load *= 1 + 0.045 * math.sin(day * 1.73 + phase)
    # Continuous low-amplitude changes, stable across browsers/reloads.
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    load *= 1 + 0.025 * math.sin(seconds / 43 + phase) + 0.015 * math.sin(seconds / 137 + phase)
    lat, lon = CITIES.get(str(p["city"]), CITIES["Ahmedabad"])
    declination = math.radians(23.44 * math.sin(math.tau * (day - 81) / 365))
    solar_noon = 12 + (82.5 - lon) / 15
    elevation = max(
        0,
        math.sin(math.radians(lat)) * math.sin(declination)
        + math.cos(math.radians(lat))
        * math.cos(declination)
        * math.cos(math.radians(15 * (hour - solar_noon))),
    )
    orientation = {"south": 1, "east": 0.86, "west": 0.86, "north": 0.7}[str(p["orientation"])]
    tilt = max(0.65, math.cos(math.radians(float(p["tilt"]) - lat)))
    solar = capacity * elevation * 0.82 * orientation * tilt
    solar *= 0.97 + 0.03 * math.sin(seconds / 101 + phase)
    generation, demand = round(solar, 4), round(load, 4)
    return {
        "generation_kw": generation,
        "load_kw": demand,
        "grid_import_kw": round(max(0, demand - generation), 4),
        "grid_export_kw": round(max(0, generation - demand), 4),
    }


def interval(
    moment: datetime, capacity: float, settings: dict[str, Any], seed: str, scenario: str = "normal"
) -> dict[str, Decimal]:
    # Three midpoint samples integrate the 15-minute interval. Import/export are
    # integrated separately so transitions around sunrise retain energy balance.
    samples = [
        power(moment + timedelta(minutes=2.5 + 5 * i), capacity, settings, seed) for i in range(3)
    ]
    if scenario != "normal":
        for sample in samples:
            if scenario == "cloudy":
                sample["generation_kw"] *= 0.28
            if scenario == "congestion":
                sample["load_kw"] += 65
            sample["grid_import_kw"] = max(0, sample["load_kw"] - sample["generation_kw"])
            sample["grid_export_kw"] = max(0, sample["generation_kw"] - sample["load_kw"])
    result = {
        key: Decimal(str(sum(sample[key] for sample in samples) / 3)).quantize(Decimal(".0001"))
        for key in samples[0]
    }
    # Reconcile rounding at the power boundary.
    result["grid_export_kw"] = max(
        result["grid_export_kw"], result["generation_kw"] - result["load_kw"], Decimal(0)
    )
    result["grid_import_kw"] = (
        result["load_kw"] + result["grid_export_kw"] - result["generation_kw"]
    )
    for key, value in list(result.items()):
        result[key + "h"] = value / 4
    return result
