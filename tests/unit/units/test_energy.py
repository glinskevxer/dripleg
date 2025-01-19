from __future__ import annotations

import pytest

from dripleg.errors import UnitError, ValidationError
from dripleg.units.energy import Energy, EnergyRate, EnergyUnit, SpecificEnthalpy
from dripleg.units.flow import Mass, MassFlow


def test_a_million_btu_is_an_mmbtu() -> None:
    assert Energy.from_mmbtu(1.0).btu == pytest.approx(1_000_000.0)
    assert Energy.from_btu(2_500_000.0).mmbtu == pytest.approx(2.5)


def test_metric_and_electrical_units() -> None:
    assert Energy.from_megajoules(1.0).btu == pytest.approx(947.817, abs=0.01)
    assert Energy.from_gigajoules(1.0).megajoules == pytest.approx(1000.0)
    assert Energy.from_kilowatt_hours(1.0).btu == pytest.approx(3412.14, abs=0.01)
    assert Energy.from_btu(3412.14).kilowatt_hours == pytest.approx(1.0, abs=0.001)
    assert Energy.from_mmbtu(1.0).gigajoules == pytest.approx(1.0551, abs=0.001)


def test_a_therm_is_a_hundred_thousand_btu() -> None:
    assert Energy.from_therms(10.0).mmbtu == pytest.approx(1.0)
    assert Energy.from_mmbtu(1.0).therms == pytest.approx(10.0)


def test_of_and_parse_read_the_trade_spellings() -> None:
    assert Energy.of(1.0, "dekatherm") == Energy.of(1.0, EnergyUnit.MMBTU)
    assert Energy.of(1.0, "DTH").mmbtu == pytest.approx(1.0)
    assert Energy.parse("2.5 MMBtu").mmbtu == pytest.approx(2.5)


def test_bad_energy_units() -> None:
    with pytest.raises(UnitError, match="unknown energy unit"):
        Energy.of(1.0, "calories")
    with pytest.raises(UnitError, match="no unit"):
        Energy.parse("2.5")
    with pytest.raises(ValidationError, match="cannot read"):
        Energy.parse("a lot")


def test_energy_is_never_negative() -> None:
    with pytest.raises(ValidationError, match="cannot be negative"):
        Energy.from_btu(-1.0)
    with pytest.raises(ValidationError, match="finite"):
        Energy.from_btu(float("nan"))
    assert Energy.zero().btu == 0.0


def test_energy_adds_and_scales() -> None:
    total = Energy.from_mmbtu(1.0) + Energy.from_mmbtu(0.5)
    assert total.mmbtu == pytest.approx(1.5)
    assert (total * 2).mmbtu == pytest.approx(3.0)


def test_dividing_by_boiler_efficiency_raises_the_fuel_bill() -> None:
    fuel = Energy.from_mmbtu(80.0).divided_by_efficiency(0.80)
    assert fuel.mmbtu == pytest.approx(100.0)


def test_efficiency_has_to_be_a_fraction() -> None:
    for bad in (0.0, -0.5, 1.2):
        with pytest.raises(ValidationError, match="efficiency"):
            Energy.from_mmbtu(1.0).divided_by_efficiency(bad)


def test_energy_over_a_run_is_a_rate() -> None:
    rate = Energy.from_mmbtu(8.76).over(8760.0)
    assert rate.btu_per_hour == pytest.approx(1000.0)
    with pytest.raises(ValidationError, match="longer than zero"):
        Energy.from_mmbtu(1.0).over(0.0)


def test_rate_units() -> None:
    assert EnergyRate.from_kilowatts(1.0).btu_per_hour == pytest.approx(3412.14, abs=0.01)
    assert EnergyRate.from_boiler_horsepower(1.0).btu_per_hour == pytest.approx(33475.0)
    rate = EnergyRate.from_btu_per_hour(33475.0)
    assert rate.boiler_horsepower == pytest.approx(1.0)
    assert rate.kilowatts == pytest.approx(9.81, abs=0.01)
    assert rate.mmbtu_per_hour == pytest.approx(0.033475)


def test_rate_over_a_year_defaults_to_full_hours() -> None:
    assert EnergyRate.from_btu_per_hour(1000.0).over().mmbtu == pytest.approx(8.76)
    assert EnergyRate.from_btu_per_hour(1000.0).over(4000.0).mmbtu == pytest.approx(4.0)


def test_rates_add_and_refuse_rubbish() -> None:
    total = EnergyRate.from_kilowatts(1.0) + EnergyRate.from_kilowatts(2.0)
    assert total.kilowatts == pytest.approx(3.0)
    with pytest.raises(ValidationError, match="cannot be negative"):
        EnergyRate.from_btu_per_hour(-1.0)
    with pytest.raises(ValidationError, match="not finite"):
        EnergyRate.from_btu_per_hour(float("inf"))
    with pytest.raises(ValidationError, match="hours cannot be negative"):
        EnergyRate.from_btu_per_hour(1.0).over(-1.0)


def test_enthalpy_times_a_mass_is_an_energy() -> None:
    latent = SpecificEnthalpy.from_btu_per_pound(870.0)
    assert latent.carried_by(Mass.from_pounds(1000.0)).btu == pytest.approx(870_000.0)


def test_enthalpy_times_a_rate_is_a_rate() -> None:
    latent = SpecificEnthalpy.from_btu_per_pound(870.0)
    assert latent.carried_at(MassFlow.from_pounds_per_hour(50.0)).btu_per_hour == pytest.approx(
        43_500.0
    )


def test_enthalpy_metric_round_trip() -> None:
    h = SpecificEnthalpy.from_kilojoules_per_kilogram(2676.0)
    assert h.btu_per_pound == pytest.approx(1150.5, abs=0.5)
    assert h.kilojoules_per_kilogram == pytest.approx(2676.0, abs=0.5)


def test_enthalpy_subtracts_to_a_latent_heat() -> None:
    steam = SpecificEnthalpy.from_btu_per_pound(1193.0)
    water = SpecificEnthalpy.from_btu_per_pound(324.0)
    assert (steam - water).btu_per_pound == pytest.approx(869.0)
    assert (water + (steam - water)).btu_per_pound == pytest.approx(1193.0)


def test_enthalpy_may_be_negative_because_it_is_read_off_a_datum() -> None:
    assert SpecificEnthalpy.from_btu_per_pound(-5.0).btu_per_pound == pytest.approx(-5.0)
    with pytest.raises(ValidationError, match="not finite"):
        SpecificEnthalpy.from_btu_per_pound(float("nan"))


def test_printing() -> None:
    assert str(Energy.from_mmbtu(2.5)) == "2.5 MMBtu"
    assert str(Energy.from_btu(1500.0)) == "1,500 Btu"
    assert str(EnergyRate.from_btu_per_hour(43500.0)) == "43,500 Btu/h"
    assert str(SpecificEnthalpy.from_btu_per_pound(870.0)) == "870.0 Btu/lb"
