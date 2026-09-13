from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.api.v1.household import HouseholdSetup
from app.domain.policies.community_energy import IST
from app.domain.policies.household_energy import DEFAULTS, interval, power


def test_monthly_calibration_night_solar_and_energy_conservation():
    start = datetime(2026, 9, 13, tzinfo=IST)
    records = [
        interval(start + timedelta(minutes=15 * i), 6, DEFAULTS, "home-one") for i in range(96)
    ]
    daily = sum(r["load_kwh"] for r in records)
    assert abs(float(daily) - DEFAULTS["monthly_kwh"] / 30) < 0.65
    for record in records:
        assert all(value >= 0 for value in record.values())
        assert (
            record["generation_kwh"] + record["grid_import_kwh"]
            == record["load_kwh"] + record["grid_export_kwh"]
        )
    assert records[0]["generation_kw"] == 0
    assert records[48]["generation_kw"] > Decimal(3)


def test_profiles_are_personal_reproducible_and_continuously_changing():
    moment = datetime(2026, 9, 13, 12, tzinfo=IST)
    first = power(moment, 6, DEFAULTS, "home-one")
    assert first == power(moment, 6, DEFAULTS, "home-one")
    assert first != power(moment + timedelta(seconds=5), 6, DEFAULTS, "home-one")
    assert first != power(moment, 6, DEFAULTS, "home-two")
    larger = power(moment, 6, DEFAULTS | {"monthly_kwh": 720}, "home-one")
    assert larger["load_kw"] == pytest.approx(first["load_kw"] * 2, abs=0.0001)
    assert power(moment, 0, DEFAULTS, "home-one")["generation_kw"] == 0
    assert (
        power(moment, 6, DEFAULTS | {"orientation": "north"}, "home-one")["generation_kw"]
        < first["generation_kw"]
    )


def test_setup_rejects_untrusted_photo_and_invalid_profile_values():
    for fields in (
        {"avatar": "https://example.com/person.svg"},
        {"photo": "data:image/svg+xml;base64,PHN2Zz4="},
        {"monthly_kwh": -1},
        {"occupants": 0},
    ):
        with pytest.raises(ValueError):
            HouseholdSetup(**fields)
