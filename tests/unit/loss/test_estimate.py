from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.loss.estimate import estimate_steam_loss
from dripleg.loss.napier import SHARP_ORIFICE_CD, WORN_SEAT_CD
from dripleg.model.operating import OperatingProfile, ServicePattern
from dripleg.survey.condition import TrapCondition
from dripleg.units.pressure import Pressure
from tests.support.build import a_header, a_model, a_station


def test_a_healthy_trap_loses_nothing_but_still_gets_a_row() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.OK)
    assert loss.flow.is_zero
    assert not loss.is_losing
    assert loss.pounds_per_year == pytest.approx(0.0)
    assert str(loss) == "B12-MP-0043 losing nothing"


def test_a_blowing_trap_loses_the_whole_seat() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH)
    assert loss.open_fraction == 1.0
    assert loss.discharge_coefficient == WORN_SEAT_CD
    assert loss.flow.pounds_per_hour > 30.0
    assert loss.is_losing


def test_a_leaking_trap_loses_a_quarter_of_it() -> None:
    blowing = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH)
    leaking = estimate_steam_loss(a_station(), TrapCondition.LEAKING)
    assert leaking.open_fraction == 0.25
    assert leaking.discharge_coefficient == SHARP_ORIFICE_CD
    ratio = leaking.flow.pounds_per_hour / blowing.flow.pounds_per_hour
    assert ratio == pytest.approx(0.25 * SHARP_ORIFICE_CD / WORN_SEAT_CD, abs=0.01)


def test_a_cold_trap_wastes_no_steam() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.FAILED_CLOSED)
    assert loss.flow.is_zero
    assert loss.open_fraction == 0.0


def test_the_annual_figure_is_the_rate_times_the_live_hours() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH)
    assert loss.hours_per_year == pytest.approx(8760.0)
    assert loss.pounds_per_year == pytest.approx(loss.flow.pounds_per_hour * 8760.0)


def test_a_seasonal_leg_loses_for_part_of_the_year() -> None:
    heating = OperatingProfile("HEAT", "Building heating", ServicePattern.HEATING_SEASON)
    seasonal = estimate_steam_loss(a_station(profile=heating), TrapCondition.BLOWING_THROUGH)
    continuous = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH)
    assert seasonal.flow == continuous.flow
    assert seasonal.pounds_per_year == pytest.approx(continuous.pounds_per_year * 7 / 12)


def test_a_measured_pressure_is_used_when_given() -> None:
    register = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH)
    measured = estimate_steam_loss(
        a_station(), TrapCondition.BLOWING_THROUGH, pressure=Pressure.from_psig(60.0)
    )
    assert measured.pressure.psig == pytest.approx(60.0)
    assert measured.flow.pounds_per_hour < register.flow.pounds_per_hour


def test_a_measured_pressure_below_the_return_line_is_refused() -> None:
    with pytest.raises(ValidationError, match="above the measured inlet"):
        estimate_steam_loss(
            a_station(),
            TrapCondition.BLOWING_THROUGH,
            pressure=Pressure.from_psig(5.0),
        )


def test_the_open_fraction_can_be_overridden_from_a_measurement() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.LEAKING, open_fraction=0.6)
    assert loss.open_fraction == pytest.approx(0.6)
    with pytest.raises(ValidationError, match="open fraction sits in"):
        estimate_steam_loss(a_station(), TrapCondition.LEAKING, open_fraction=1.5)


def test_the_hours_can_be_overridden_for_a_shortened_year() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH, hours_per_year=2000.0)
    assert loss.pounds_per_year == pytest.approx(loss.flow.pounds_per_hour * 2000.0)


def test_negative_hours_are_refused() -> None:
    with pytest.raises(ValidationError, match="no negative hours"):
        estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH, hours_per_year=-1.0)


def test_a_bigger_orifice_loses_more() -> None:
    small = estimate_steam_loss(
        a_station(model=a_model(orifice=0.093)), TrapCondition.BLOWING_THROUGH
    )
    big = estimate_steam_loss(
        a_station(model=a_model(orifice=0.186)), TrapCondition.BLOWING_THROUGH
    )
    assert big.flow.pounds_per_hour == pytest.approx(4 * small.flow.pounds_per_hour)


def test_a_high_return_pressure_cuts_the_loss() -> None:
    free = estimate_steam_loss(
        a_station(header=a_header(operating=30.0, discharge=5.0)),
        TrapCondition.BLOWING_THROUGH,
    )
    loaded = estimate_steam_loss(
        a_station(header=a_header(operating=30.0, discharge=25.0)),
        TrapCondition.BLOWING_THROUGH,
    )
    assert loaded.flow.pounds_per_hour < free.flow.pounds_per_hour


def test_the_assumptions_are_printed_in_order() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.LEAKING)
    lines = loss.assumptions()
    assert len(lines) == 5
    assert lines[0].startswith("orifice 0.093 in")
    assert "25% of the seat passing, from the leaking code" in lines[1]
    assert "discharge coefficient 0.61" in lines[2]
    assert "125.0 psig inlet against 15.0 psig discharge" in lines[3]
    assert "8,760 live hours" in lines[4]


def test_printing_a_loss() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH)
    printed = str(loss)
    assert printed.startswith("B12-MP-0043 losing ")
    assert "lb/h" in printed
    assert "a year" in printed


def test_a_trap_with_no_live_hours_loses_nothing() -> None:
    loss = estimate_steam_loss(a_station(), TrapCondition.BLOWING_THROUGH, hours_per_year=0.0)
    assert not loss.is_losing
    assert loss.pounds_per_year == 0.0
