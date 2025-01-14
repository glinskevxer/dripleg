from __future__ import annotations

import pytest

from dripleg.errors import UnitError, ValidationError
from dripleg.units.flow import HOURS_PER_YEAR, Mass, MassFlow, MassFlowUnit, MassUnit


def test_pounds_and_kilograms_agree() -> None:
    assert Mass.from_kilograms(1000.0).pounds == pytest.approx(2204.62, abs=0.01)
    assert Mass.from_pounds(2204.62).kilograms == pytest.approx(1000.0, abs=0.01)


def test_tonnes_and_short_tons_are_not_the_same_ton() -> None:
    assert Mass.from_tonnes(1.0).pounds == pytest.approx(2204.62, abs=0.01)
    assert Mass.from_short_tons(1.0).pounds == pytest.approx(2000.0)
    assert Mass.from_pounds(4409.24).tonnes == pytest.approx(2.0, abs=0.001)
    assert Mass.from_pounds(4000.0).short_tons == pytest.approx(2.0)


def test_mass_of_takes_a_spelling() -> None:
    assert Mass.of(1.0, "tonne") == Mass.of(1000.0, MassUnit.KILOGRAM)
    assert Mass.of(5.0, "LBS").pounds == pytest.approx(5.0)


def test_mass_of_refuses_nonsense() -> None:
    with pytest.raises(UnitError, match="unknown mass unit"):
        Mass.of(1.0, "barrels")


def test_negative_mass_is_refused() -> None:
    with pytest.raises(ValidationError, match="cannot be negative"):
        Mass.from_pounds(-1.0)
    with pytest.raises(ValidationError, match="finite"):
        Mass.from_pounds(float("nan"))


def test_masses_add_and_scale() -> None:
    total = Mass.from_pounds(100.0) + Mass.from_pounds(250.0)
    assert total.pounds == pytest.approx(350.0)
    assert (total * 2).pounds == pytest.approx(700.0)


def test_a_mass_spread_over_a_run_is_a_rate() -> None:
    rate = Mass.from_pounds(8760.0).over(8760.0)
    assert rate.pounds_per_hour == pytest.approx(1.0)


def test_a_run_of_no_hours_is_refused() -> None:
    with pytest.raises(ValidationError, match="longer than zero"):
        Mass.from_pounds(10.0).over(0.0)


def test_flow_units_convert() -> None:
    assert MassFlow.from_kilograms_per_hour(100.0).pounds_per_hour == pytest.approx(
        220.46, abs=0.01
    )
    assert MassFlow.from_tonnes_per_hour(1.0).tonnes_per_hour == pytest.approx(1.0)
    assert MassFlow.from_pounds_per_hour(220.46).kilograms_per_hour == pytest.approx(
        100.0, abs=0.01
    )


def test_flow_of_and_parse() -> None:
    assert MassFlow.of(50.0, "pph") == MassFlow.of(50.0, MassFlowUnit.POUND_PER_HOUR)
    assert MassFlow.parse("50 lb/h").pounds_per_hour == pytest.approx(50.0)
    assert MassFlow.parse("22.68 kg/hr").pounds_per_hour == pytest.approx(50.0, abs=0.01)


def test_flow_parse_needs_a_unit_it_knows() -> None:
    with pytest.raises(UnitError, match="no unit"):
        MassFlow.parse("50")
    with pytest.raises(UnitError, match="unknown flow unit"):
        MassFlow.parse("50 gpm")
    with pytest.raises(ValidationError, match="cannot read"):
        MassFlow.parse("lots")


def test_zero_flow_knows_itself() -> None:
    assert MassFlow.zero().is_zero
    assert not MassFlow.from_pounds_per_hour(0.5).is_zero


def test_negative_flow_is_refused() -> None:
    with pytest.raises(ValidationError, match="cannot be negative"):
        MassFlow.from_pounds_per_hour(-3.0)
    with pytest.raises(ValidationError, match="finite"):
        MassFlow.from_pounds_per_hour(float("inf"))


def test_a_rate_over_hours_is_a_mass() -> None:
    lost = MassFlow.from_pounds_per_hour(48.0).over(2000.0)
    assert lost.pounds == pytest.approx(96000.0)


def test_annual_defaults_to_a_full_year() -> None:
    assert HOURS_PER_YEAR == 8760.0
    assert MassFlow.from_pounds_per_hour(1.0).annual().pounds == pytest.approx(8760.0)
    assert MassFlow.from_pounds_per_hour(1.0).annual(4000.0).pounds == pytest.approx(4000.0)


def test_negative_hours_are_refused() -> None:
    with pytest.raises(ValidationError, match="hours cannot be negative"):
        MassFlow.from_pounds_per_hour(1.0).over(-1.0)


def test_scaling_a_flow_by_a_severity_factor() -> None:
    assert MassFlow.from_pounds_per_hour(100.0).scaled(0.25).pounds_per_hour == pytest.approx(25.0)
    with pytest.raises(ValidationError, match="factor cannot be negative"):
        MassFlow.from_pounds_per_hour(100.0).scaled(-0.5)


def test_flows_add_and_sort() -> None:
    total = MassFlow.from_pounds_per_hour(10.0) + MassFlow.from_pounds_per_hour(15.0)
    assert total.pounds_per_hour == pytest.approx(25.0)
    ranked = sorted([total, MassFlow.zero()], reverse=True)
    assert ranked[0] == total


def test_printing() -> None:
    assert str(MassFlow.from_pounds_per_hour(1234.5)) == "1,234.5 lb/h"
    assert str(Mass.from_pounds(96000.0)) == "96,000 lb"
    assert str(Mass.from_pounds(3_500_000.0)) == "3.50 Mlb"
