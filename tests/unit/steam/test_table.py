from __future__ import annotations

import pytest

from dripleg.errors import OutOfRangeError, ValidationError
from dripleg.steam.table import (
    SATURATION_TABLE,
    TABLE_MAX_PSIA,
    TABLE_MIN_PSIA,
    SaturationPoint,
    row_bracketing_pressure,
    row_bracketing_temperature,
)
from dripleg.units.energy import SpecificEnthalpy
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature


def test_the_table_is_sorted_by_pressure() -> None:
    pressures = [p.pressure.psia for p in SATURATION_TABLE]
    assert pressures == sorted(pressures)
    assert len(set(pressures)) == len(pressures)


def test_temperature_climbs_with_pressure() -> None:
    temperatures = [p.temperature.fahrenheit for p in SATURATION_TABLE]
    assert temperatures == sorted(temperatures)


def test_latent_heat_falls_as_pressure_climbs() -> None:
    latent = [p.latent_heat.btu_per_pound for p in SATURATION_TABLE]
    assert latent == sorted(latent, reverse=True)


def test_specific_volume_falls_as_pressure_climbs() -> None:
    volumes = [p.vapour_specific_volume for p in SATURATION_TABLE]
    assert volumes == sorted(volumes, reverse=True)


def test_every_row_adds_up() -> None:
    for point in SATURATION_TABLE:
        total = point.liquid_enthalpy.btu_per_pound + point.latent_heat.btu_per_pound
        assert total == pytest.approx(point.vapour_enthalpy.btu_per_pound, abs=0.06)


def test_atmospheric_row_is_the_one_everybody_knows() -> None:
    atmospheric = next(p for p in SATURATION_TABLE if p.pressure.psia == pytest.approx(14.696))
    assert atmospheric.temperature.fahrenheit == pytest.approx(212.0)
    assert atmospheric.latent_heat.btu_per_pound == pytest.approx(970.3, abs=0.1)


def test_the_ends_of_the_table_are_published() -> None:
    assert pytest.approx(SATURATION_TABLE[0].pressure.psia) == TABLE_MIN_PSIA
    assert pytest.approx(SATURATION_TABLE[-1].pressure.psia) == TABLE_MAX_PSIA


def test_density_is_the_reciprocal_of_specific_volume() -> None:
    point = SATURATION_TABLE[-1]
    assert point.vapour_density == pytest.approx(1.0 / point.vapour_specific_volume)


def test_sensible_heat_is_measured_above_a_feedwater_datum() -> None:
    point = row_bracketing_pressure(100.0)[0]
    above = point.sensible_heat_above(Temperature.from_fahrenheit(212.0))
    assert above.btu_per_pound == pytest.approx(298.54 - 180.0, abs=0.1)


def test_a_row_that_does_not_add_up_is_refused() -> None:
    with pytest.raises(ValidationError, match="away from hg"):
        SaturationPoint(
            pressure=Pressure.from_psia(100.0),
            temperature=Temperature.from_fahrenheit(327.82),
            liquid_enthalpy=SpecificEnthalpy.from_btu_per_pound(298.5),
            latent_heat=SpecificEnthalpy.from_btu_per_pound(888.6),
            vapour_enthalpy=SpecificEnthalpy.from_btu_per_pound(1000.0),
            vapour_specific_volume=4.432,
        )


def test_a_row_with_no_volume_is_refused() -> None:
    with pytest.raises(ValidationError, match="specific volume"):
        SaturationPoint(
            pressure=Pressure.from_psia(100.0),
            temperature=Temperature.from_fahrenheit(327.82),
            liquid_enthalpy=SpecificEnthalpy.from_btu_per_pound(298.54),
            latent_heat=SpecificEnthalpy.from_btu_per_pound(888.6),
            vapour_enthalpy=SpecificEnthalpy.from_btu_per_pound(1187.2),
            vapour_specific_volume=0.0,
        )


def test_bracketing_an_exact_row_gives_it_twice() -> None:
    low, high = row_bracketing_pressure(100.0)
    assert low is high
    assert low.temperature.fahrenheit == pytest.approx(327.82)


def test_bracketing_between_rows() -> None:
    low, high = row_bracketing_pressure(110.0)
    assert low.pressure.psia == pytest.approx(100.0)
    assert high.pressure.psia == pytest.approx(120.0)


def test_bracketing_the_last_row() -> None:
    low, high = row_bracketing_pressure(TABLE_MAX_PSIA)
    assert low is high
    assert low.pressure.psia == pytest.approx(1000.0)


def test_off_the_end_of_the_table_raises_rather_than_guessing() -> None:
    with pytest.raises(OutOfRangeError) as caught:
        row_bracketing_pressure(1200.0)
    assert caught.value.high == pytest.approx(TABLE_MAX_PSIA)
    assert caught.value.value == pytest.approx(1200.0)
    with pytest.raises(OutOfRangeError):
        row_bracketing_pressure(0.1)


def test_bracketing_by_temperature_walks_the_other_column() -> None:
    low, high = row_bracketing_temperature(300.0)
    assert low.pressure.psia == pytest.approx(60.0)
    assert high.pressure.psia == pytest.approx(70.0)
    exact_low, exact_high = row_bracketing_temperature(212.0)
    assert exact_low is exact_high


def test_temperature_bracketing_has_its_own_range_guard() -> None:
    with pytest.raises(OutOfRangeError, match="outside the table"):
        row_bracketing_temperature(600.0)
    with pytest.raises(OutOfRangeError):
        row_bracketing_temperature(60.0)


def test_the_top_of_the_temperature_column_brackets_to_itself() -> None:
    low, high = row_bracketing_temperature(544.61)
    assert low is high
    assert low.pressure.psia == pytest.approx(1000.0)
