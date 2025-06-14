from __future__ import annotations

import math

import pytest

from dripleg.errors import ValidationError
from dripleg.loss.napier import (
    CRITICAL_PRESSURE_RATIO,
    NAPIER_CONSTANT,
    SHARP_ORIFICE_CD,
    WORN_SEAT_CD,
    back_pressure_factor,
    orifice_area,
    orifice_flow,
)
from dripleg.units.pressure import Pressure


def test_the_orifice_area_is_the_circle() -> None:
    assert orifice_area(0.125) == pytest.approx(math.pi * 0.0625**2)
    assert orifice_area(1.0) == pytest.approx(math.pi / 4.0)


def test_an_orifice_that_is_not_a_trap_orifice() -> None:
    with pytest.raises(ValidationError, match="not a trap orifice diameter"):
        orifice_area(0.0)
    with pytest.raises(ValidationError, match="not a trap orifice diameter"):
        orifice_area(4.0)


def test_a_choked_seat_ignores_the_back_pressure() -> None:
    upstream = Pressure.from_psig(125.0)
    assert back_pressure_factor(upstream, Pressure.from_psig(0.0)) == 1.0
    assert back_pressure_factor(upstream, Pressure.from_psig(15.0)) == 1.0
    assert back_pressure_factor(upstream, Pressure.from_psia(upstream.psia * 0.5)) == 1.0


def test_the_factor_falls_away_above_the_critical_ratio() -> None:
    upstream = Pressure.from_psia(100.0)
    at_critical = back_pressure_factor(
        upstream, Pressure.from_psia(100.0 * CRITICAL_PRESSURE_RATIO)
    )
    part_way = back_pressure_factor(upstream, Pressure.from_psia(80.0))
    nearly_equal = back_pressure_factor(upstream, Pressure.from_psia(99.0))
    assert at_critical == pytest.approx(1.0)
    assert 0.0 < nearly_equal < part_way < 1.0


def test_equal_pressures_pass_nothing() -> None:
    upstream = Pressure.from_psia(100.0)
    assert back_pressure_factor(upstream, upstream) == pytest.approx(0.0)


def test_back_pressure_above_the_steam_is_refused() -> None:
    with pytest.raises(ValidationError, match="cannot be above the steam pressure"):
        back_pressure_factor(Pressure.from_psia(50.0), Pressure.from_psia(100.0))


def test_no_upstream_pressure_at_all() -> None:
    with pytest.raises(ValidationError, match="no flow from no pressure"):
        back_pressure_factor(Pressure.from_psia(0.0), Pressure.from_psia(0.0))


def test_napier_is_a_straight_line_in_pressure() -> None:
    small = orifice_flow(Pressure.from_psia(100.0), 0.125)
    big = orifice_flow(Pressure.from_psia(200.0), 0.125)
    assert big.pounds_per_hour == pytest.approx(2 * small.pounds_per_hour)


def test_a_known_orifice_at_a_known_pressure() -> None:
    # An eighth inch hole at 100 psia, sharp edged.
    area = math.pi * 0.0625**2
    expected = NAPIER_CONSTANT * SHARP_ORIFICE_CD * area * 100.0
    assert orifice_flow(Pressure.from_psia(100.0), 0.125).pounds_per_hour == pytest.approx(expected)
    assert expected == pytest.approx(38.5, abs=0.1)


def test_a_worn_seat_passes_more_than_a_sharp_one() -> None:
    sharp = orifice_flow(Pressure.from_psig(125.0), 0.093)
    worn = orifice_flow(Pressure.from_psig(125.0), 0.093, discharge_coefficient=WORN_SEAT_CD)
    assert worn.pounds_per_hour > sharp.pounds_per_hour
    assert worn.pounds_per_hour / sharp.pounds_per_hour == pytest.approx(
        WORN_SEAT_CD / SHARP_ORIFICE_CD
    )


def test_flow_goes_with_the_square_of_the_diameter() -> None:
    small = orifice_flow(Pressure.from_psig(125.0), 0.1)
    big = orifice_flow(Pressure.from_psig(125.0), 0.2)
    assert big.pounds_per_hour == pytest.approx(4 * small.pounds_per_hour)


def test_a_partly_open_seat_passes_its_share() -> None:
    whole = orifice_flow(Pressure.from_psig(125.0), 0.093)
    quarter = orifice_flow(Pressure.from_psig(125.0), 0.093, open_fraction=0.25)
    assert quarter.pounds_per_hour == pytest.approx(whole.pounds_per_hour * 0.25)


def test_a_shut_seat_passes_nothing() -> None:
    assert orifice_flow(Pressure.from_psig(125.0), 0.093, open_fraction=0.0).is_zero


def test_a_back_pressure_below_critical_changes_nothing() -> None:
    free = orifice_flow(Pressure.from_psig(125.0), 0.093)
    against = orifice_flow(Pressure.from_psig(125.0), 0.093, downstream=Pressure.from_psig(15.0))
    assert against.pounds_per_hour == pytest.approx(free.pounds_per_hour)


def test_a_high_back_pressure_cuts_the_flow() -> None:
    free = orifice_flow(Pressure.from_psig(30.0), 0.093)
    against = orifice_flow(Pressure.from_psig(30.0), 0.093, downstream=Pressure.from_psig(25.0))
    assert against.pounds_per_hour < free.pounds_per_hour * 0.8


def test_bad_coefficients_and_fractions_are_refused() -> None:
    for bad in (0.0, -0.5, 1.5):
        with pytest.raises(ValidationError, match="discharge coefficient sits in"):
            orifice_flow(Pressure.from_psig(125.0), 0.093, discharge_coefficient=bad)
    for bad_fraction in (-0.1, 1.4):
        with pytest.raises(ValidationError, match="open fraction of a seat"):
            orifice_flow(Pressure.from_psig(125.0), 0.093, open_fraction=bad_fraction)


def test_a_realistic_failed_trap_is_tens_of_pounds_an_hour() -> None:
    # A quarter inch seat blowing through on a 125 psig header.
    flow = orifice_flow(
        Pressure.from_psig(125.0),
        0.25,
        downstream=Pressure.from_psig(15.0),
        discharge_coefficient=WORN_SEAT_CD,
    )
    assert 100.0 < flow.pounds_per_hour < 400.0


def test_a_small_leak_is_a_handful_of_pounds_an_hour() -> None:
    flow = orifice_flow(Pressure.from_psig(125.0), 0.093, open_fraction=0.25)
    assert 5.0 < flow.pounds_per_hour < 12.0
