from __future__ import annotations

import pytest

from dripleg.errors import UnitError, ValidationError
from dripleg.units.pressure import ATMOSPHERE_PSIA, Pressure, PressureUnit


def test_gauge_and_absolute_differ_by_one_atmosphere() -> None:
    header = Pressure.from_psig(125.0)
    assert header.psia == pytest.approx(125.0 + ATMOSPHERE_PSIA)
    assert header.psig == pytest.approx(125.0)


def test_absolute_constructor_keeps_the_number() -> None:
    assert Pressure.from_psia(139.7).psia == pytest.approx(139.7)


def test_atmosphere_reads_as_zero_gauge() -> None:
    assert Pressure.from_psia(ATMOSPHERE_PSIA).psig == pytest.approx(0.0)


def test_bar_round_trips_through_psi() -> None:
    p = Pressure.from_barg(8.62)
    assert p.barg == pytest.approx(8.62)
    assert p.psig == pytest.approx(125.02, abs=0.05)


def test_bar_absolute_round_trips() -> None:
    p = Pressure.from_bara(10.0)
    assert p.bara == pytest.approx(10.0)
    assert p.psia == pytest.approx(145.038, abs=0.01)


def test_kilopascal_both_zeros() -> None:
    assert Pressure.from_kpa_absolute(101.325).psig == pytest.approx(0.0, abs=0.001)
    assert Pressure.from_kpa_gauge(0.0).psig == pytest.approx(0.0)
    assert Pressure.from_kpa_gauge(862.0).kpa_gauge == pytest.approx(862.0)


def test_kilopascal_absolute_reads_back() -> None:
    assert Pressure.from_psig(125.0).kpa_absolute == pytest.approx(963.2, abs=0.5)


def test_vacuum_in_inches_of_mercury_lands_below_atmosphere() -> None:
    p = Pressure.from_inches_mercury_vacuum(26.0)
    assert p.is_vacuum
    assert p.psia == pytest.approx(1.926, abs=0.01)


def test_vacuum_is_quoted_positive() -> None:
    with pytest.raises(ValidationError, match="quoted positive"):
        Pressure.from_inches_mercury_vacuum(-4.0)


def test_inches_of_water_is_a_gauge_unit() -> None:
    p = Pressure.from_inches_water_gauge(27.7)
    assert p.psig == pytest.approx(1.0, abs=0.005)


def test_a_header_at_atmosphere_is_not_vacuum() -> None:
    assert not Pressure.from_psig(0.0).is_vacuum


def test_of_accepts_the_enum_and_the_spelling() -> None:
    assert Pressure.of(125.0, PressureUnit.PSIG) == Pressure.of(125.0, "psig")
    assert Pressure.of(125.0, "PSI G").psig == pytest.approx(125.0)
    assert Pressure.of(10.0, "bar_a").bara == pytest.approx(10.0)


def test_of_refuses_an_unknown_unit() -> None:
    with pytest.raises(UnitError, match="unknown pressure unit"):
        Pressure.of(4.0, "furlongs")


def test_parse_reads_a_spreadsheet_cell() -> None:
    assert Pressure.parse(" 125 psig ").psig == pytest.approx(125.0)
    assert Pressure.parse("14.7psia").psia == pytest.approx(14.7)


def test_parse_refuses_a_bare_number() -> None:
    with pytest.raises(UnitError, match="no unit"):
        Pressure.parse("125")


def test_parse_refuses_rubbish() -> None:
    with pytest.raises(ValidationError, match="cannot read"):
        Pressure.parse("high")


def test_negative_absolute_pressure_is_refused() -> None:
    with pytest.raises(ValidationError, match="cannot be negative"):
        Pressure.from_psia(-1.0)


def test_a_deep_vacuum_gauge_reading_is_still_legal() -> None:
    assert Pressure.from_psig(-14.0).psia == pytest.approx(0.696, abs=0.001)


def test_not_a_number_is_refused() -> None:
    with pytest.raises(ValidationError, match="finite"):
        Pressure.from_psia(float("nan"))


def test_ratio_is_absolute_over_absolute() -> None:
    upstream = Pressure.from_psig(125.0)
    downstream = Pressure.from_psig(15.0)
    assert downstream.ratio_to(upstream) == pytest.approx(29.696 / 139.696, abs=0.001)


def test_ratio_against_zero_is_refused() -> None:
    with pytest.raises(ValidationError, match="against zero"):
        Pressure.from_psig(10.0).ratio_to(Pressure.from_psia(0.0))


def test_ordering_is_by_absolute_pressure() -> None:
    assert Pressure.from_psig(15.0) < Pressure.from_psig(125.0)
    assert max(Pressure.from_psig(30.0), Pressure.from_barg(20.0)).psig > 200


def test_equal_pressures_compare_equal() -> None:
    assert Pressure.from_psig(0.0) == Pressure.from_psia(ATMOSPHERE_PSIA)


def test_printing_uses_gauge_above_atmosphere_and_absolute_below() -> None:
    assert str(Pressure.from_psig(125.0)) == "125.0 psig"
    assert str(Pressure.from_inches_mercury_vacuum(26.0)).endswith("psia")
    assert repr(Pressure.from_psig(125.0)).startswith("Pressure(psia=")


def test_gauge_units_know_they_are_gauge() -> None:
    assert PressureUnit.PSIG.is_gauge
    assert PressureUnit.BARG.is_gauge
    assert not PressureUnit.PSIA.is_gauge
    assert not PressureUnit.INHG_VAC.is_gauge
