from __future__ import annotations

import pytest

from dripleg.errors import OutOfRangeError, ValidationError
from dripleg.steam.saturated import (
    at_pressure,
    at_temperature,
    flash_at,
    latent_heat_at,
    saturation_pressure_at,
    saturation_temperature_at,
)
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature


def test_an_exact_row_comes_back_untouched() -> None:
    point = at_pressure(Pressure.from_psia(100.0))
    assert point.temperature.fahrenheit == pytest.approx(327.82)
    assert point.latent_heat.btu_per_pound == pytest.approx(888.7, abs=0.05)


def test_atmospheric_pressure_boils_at_two_twelve() -> None:
    assert saturation_temperature_at(Pressure.from_psig(0.0)).fahrenheit == pytest.approx(
        212.0, abs=0.05
    )


def test_a_hundred_and_twenty_five_psig_header() -> None:
    point = at_pressure(Pressure.from_psig(125.0))
    assert point.temperature.fahrenheit == pytest.approx(353.0, abs=1.0)
    assert point.latent_heat.btu_per_pound == pytest.approx(868.0, abs=3.0)


def test_interpolated_values_sit_between_the_rows() -> None:
    low = at_pressure(Pressure.from_psia(100.0))
    mid = at_pressure(Pressure.from_psia(110.0))
    high = at_pressure(Pressure.from_psia(120.0))
    assert low.temperature.fahrenheit < mid.temperature.fahrenheit < high.temperature.fahrenheit
    assert low.latent_heat.btu_per_pound > mid.latent_heat.btu_per_pound
    assert mid.latent_heat.btu_per_pound > high.latent_heat.btu_per_pound
    assert high.vapour_specific_volume < mid.vapour_specific_volume < low.vapour_specific_volume


def test_an_interpolated_point_still_adds_up() -> None:
    point = at_pressure(Pressure.from_psia(137.0))
    total = point.liquid_enthalpy.btu_per_pound + point.latent_heat.btu_per_pound
    assert total == pytest.approx(point.vapour_enthalpy.btu_per_pound)


def test_the_interpolated_pressure_is_the_one_asked_for() -> None:
    assert at_pressure(Pressure.from_psia(137.0)).pressure.psia == pytest.approx(137.0)


def test_log_interpolation_beats_straight_line_between_wide_rows() -> None:
    # Between 250 and 300 psia the published Tsat at 275 is about 409.5 F.
    # A straight line in pressure gives 409.2, log gives closer to 409.6.
    assert at_pressure(Pressure.from_psia(275.0)).temperature.fahrenheit == pytest.approx(
        409.5, abs=0.4
    )


def test_off_the_table_still_raises() -> None:
    with pytest.raises(OutOfRangeError):
        at_pressure(Pressure.from_psia(2000.0))


def test_the_inverse_lookup_finds_the_pressure() -> None:
    assert saturation_pressure_at(Temperature.from_fahrenheit(212.0)).psia == pytest.approx(
        14.696, abs=0.05
    )
    assert saturation_pressure_at(Temperature.from_fahrenheit(327.82)).psig == pytest.approx(
        85.3, abs=0.3
    )


def test_the_inverse_lookup_round_trips() -> None:
    original = Pressure.from_psig(60.0)
    back = saturation_pressure_at(saturation_temperature_at(original))
    assert back.psia == pytest.approx(original.psia, rel=0.005)


def test_the_inverse_lookup_interpolates_between_rows() -> None:
    point = at_temperature(Temperature.from_fahrenheit(300.0))
    assert 60.0 < point.pressure.psia < 70.0
    assert point.temperature.fahrenheit == pytest.approx(300.0, abs=0.4)


def test_latent_heat_shortcut_agrees_with_the_full_lookup() -> None:
    p = Pressure.from_psig(150.0)
    assert latent_heat_at(p) == at_pressure(p).latent_heat


def test_condensate_at_header_pressure_flashes_into_the_return() -> None:
    result = flash_at(Pressure.from_psig(125.0), Pressure.from_psig(15.0))
    assert result.percent == pytest.approx(12.5, abs=1.5)
    assert result.liquid_fraction == pytest.approx(1.0 - result.flash_fraction)


def test_flashing_to_atmosphere_is_the_biggest_drop() -> None:
    to_return = flash_at(Pressure.from_psig(125.0), Pressure.from_psig(15.0))
    to_air = flash_at(Pressure.from_psig(125.0), Pressure.from_psig(0.0))
    assert to_air.flash_fraction > to_return.flash_fraction


def test_no_pressure_drop_means_no_flash() -> None:
    result = flash_at(Pressure.from_psig(125.0), Pressure.from_psig(125.0))
    assert result.flash_fraction == pytest.approx(0.0)
    assert result.flash_enthalpy().btu_per_pound == pytest.approx(0.0)


def test_flash_carries_its_own_heat() -> None:
    result = flash_at(Pressure.from_psig(150.0), Pressure.from_psig(5.0))
    expected = result.flash_fraction * result.downstream.latent_heat.btu_per_pound
    assert result.flash_enthalpy().btu_per_pound == pytest.approx(expected)


def test_flash_result_keeps_both_ends() -> None:
    result = flash_at(Pressure.from_psig(125.0), Pressure.from_psig(15.0))
    assert result.upstream.pressure.psig == pytest.approx(125.0)
    assert result.downstream.pressure.psig == pytest.approx(15.0)


def test_condensate_does_not_flash_uphill() -> None:
    with pytest.raises(ValidationError, match="uphill"):
        flash_at(Pressure.from_psig(15.0), Pressure.from_psig(125.0))
