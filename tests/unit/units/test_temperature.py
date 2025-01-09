from __future__ import annotations

import pytest

from dripleg.errors import UnitError, ValidationError
from dripleg.units.temperature import (
    ABSOLUTE_ZERO_F,
    Temperature,
    TemperatureDelta,
    TemperatureUnit,
)


def test_freezing_and_boiling_line_up() -> None:
    assert Temperature.from_celsius(0.0).fahrenheit == pytest.approx(32.0)
    assert Temperature.from_celsius(100.0).fahrenheit == pytest.approx(212.0)


def test_celsius_reads_back() -> None:
    assert Temperature.from_fahrenheit(353.0).celsius == pytest.approx(178.33, abs=0.01)


def test_kelvin_and_rankine() -> None:
    assert Temperature.from_kelvin(373.15).fahrenheit == pytest.approx(212.0)
    assert Temperature.from_rankine(671.67).fahrenheit == pytest.approx(212.0)
    assert Temperature.from_fahrenheit(212.0).kelvin == pytest.approx(373.15)
    assert Temperature.from_fahrenheit(212.0).rankine == pytest.approx(671.67)


def test_absolute_zero_is_the_floor() -> None:
    assert Temperature.from_fahrenheit(ABSOLUTE_ZERO_F).kelvin == pytest.approx(0.0)
    with pytest.raises(ValidationError, match="below absolute zero"):
        Temperature.from_fahrenheit(-500.0)


def test_not_a_number_is_refused() -> None:
    with pytest.raises(ValidationError, match="finite"):
        Temperature.from_fahrenheit(float("inf"))


def test_of_takes_the_enum_or_the_spelling() -> None:
    assert Temperature.of(212.0, TemperatureUnit.FAHRENHEIT) == Temperature.of(100.0, "C")
    assert Temperature.of(100.0, "degC").fahrenheit == pytest.approx(212.0)
    assert Temperature.of(671.67, "Rankine").fahrenheit == pytest.approx(212.0)


def test_of_refuses_nonsense() -> None:
    with pytest.raises(UnitError, match="unknown temperature unit"):
        Temperature.of(4.0, "warm")


def test_parse_handles_the_degree_sign() -> None:
    assert Temperature.parse("353 F").fahrenheit == pytest.approx(353.0)
    assert Temperature.parse(" 100 °C ").fahrenheit == pytest.approx(212.0)


def test_parse_needs_a_unit() -> None:
    with pytest.raises(UnitError, match="no unit"):
        Temperature.parse("353")
    with pytest.raises(ValidationError, match="cannot read"):
        Temperature.parse("hot")


def test_subtracting_two_readings_gives_a_difference() -> None:
    upstream = Temperature.from_fahrenheit(353.0)
    downstream = Temperature.from_fahrenheit(212.0)
    gap = upstream - downstream
    assert isinstance(gap, TemperatureDelta)
    assert gap.fahrenheit == pytest.approx(141.0)


def test_a_difference_converts_by_scale_only() -> None:
    gap = TemperatureDelta.from_fahrenheit(40.0)
    assert gap.celsius == pytest.approx(22.222, abs=0.001)
    assert TemperatureDelta.from_celsius(22.222).fahrenheit == pytest.approx(40.0, abs=0.001)


def test_a_difference_may_be_negative_where_a_reading_may_not() -> None:
    gap = TemperatureDelta.from_fahrenheit(-18.0)
    assert not gap.is_rise
    assert abs(gap).fahrenheit == pytest.approx(18.0)
    assert (-gap).is_rise


def test_a_difference_that_is_not_finite_is_refused() -> None:
    with pytest.raises(ValidationError, match="not finite"):
        TemperatureDelta.from_fahrenheit(float("nan"))


def test_a_difference_off_a_reading_gives_a_reading() -> None:
    lowered = Temperature.from_fahrenheit(353.0) - TemperatureDelta.from_fahrenheit(141.0)
    assert isinstance(lowered, Temperature)
    assert lowered.fahrenheit == pytest.approx(212.0)


def test_adding_a_difference_to_a_reading() -> None:
    raised = Temperature.from_fahrenheit(212.0) + TemperatureDelta.from_fahrenheit(141.0)
    assert raised.fahrenheit == pytest.approx(353.0)


def test_adding_two_readings_is_refused() -> None:
    with pytest.raises(TypeError, match="difference"):
        Temperature.from_fahrenheit(212.0) + Temperature.from_fahrenheit(1.0)  # type: ignore[operator]


def test_differences_add_up() -> None:
    total = TemperatureDelta.from_fahrenheit(12.0) + TemperatureDelta.from_fahrenheit(-4.0)
    assert total.fahrenheit == pytest.approx(8.0)


def test_readings_sort_by_temperature() -> None:
    readings = [Temperature.from_fahrenheit(x) for x in (353.0, 212.0, 60.0)]
    assert min(readings).fahrenheit == pytest.approx(60.0)
    assert sorted(readings)[-1].fahrenheit == pytest.approx(353.0)


def test_printing() -> None:
    assert str(Temperature.from_fahrenheit(353.04)) == "353.0 F"
    assert str(TemperatureDelta.from_fahrenheit(141.0)) == "+141.0 dF"
    assert repr(Temperature.from_fahrenheit(353.0)).startswith("Temperature(")
