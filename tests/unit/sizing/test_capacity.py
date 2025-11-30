from __future__ import annotations

from dataclasses import replace

import pytest

from dripleg.errors import ValidationError
from dripleg.sizing.capacity import (
    OVERSIZE_LIMIT,
    SizingVerdict,
    check_sizing,
    condensate_capacity,
    condensate_density,
)
from dripleg.units.flow import MassFlow
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature
from tests.support.build import a_model

DIFFERENTIAL = Pressure.from_psia(110.0)
HOT = Temperature.from_fahrenheit(353.0)


def test_water_gets_lighter_as_it_gets_hotter() -> None:
    densities = [condensate_density(Temperature.from_fahrenheit(t)) for t in (60, 212, 353, 450)]
    assert densities == sorted(densities, reverse=True)


def test_the_density_table_interpolates() -> None:
    assert condensate_density(Temperature.from_fahrenheit(325.0)) == pytest.approx(56.45, abs=0.05)


def test_the_density_table_holds_at_both_ends() -> None:
    assert condensate_density(Temperature.from_fahrenheit(-20.0)) == pytest.approx(62.36)
    assert condensate_density(Temperature.from_fahrenheit(900.0)) == pytest.approx(48.95)


def test_a_disc_trap_passes_hundreds_of_pounds_an_hour() -> None:
    capacity = condensate_capacity(a_model(), DIFFERENTIAL, HOT)
    assert 500.0 < capacity.pounds_per_hour < 1200.0


def test_capacity_goes_with_the_root_of_the_differential() -> None:
    low = condensate_capacity(a_model(), Pressure.from_psia(25.0), HOT)
    high = condensate_capacity(a_model(), Pressure.from_psia(100.0), HOT)
    assert high.pounds_per_hour == pytest.approx(2 * low.pounds_per_hour)


def test_capacity_goes_with_the_square_of_the_orifice() -> None:
    small = condensate_capacity(a_model(orifice=0.1), DIFFERENTIAL, HOT)
    big = condensate_capacity(a_model(orifice=0.2), DIFFERENTIAL, HOT)
    assert big.pounds_per_hour == pytest.approx(4 * small.pounds_per_hour)


def test_a_trap_with_no_differential_passes_nothing_and_says_so() -> None:
    with pytest.raises(ValidationError, match="needs a differential"):
        condensate_capacity(a_model(), Pressure.from_psia(0.0), HOT)


def test_a_daft_discharge_coefficient_is_refused() -> None:
    with pytest.raises(ValidationError, match="discharge coefficient"):
        condensate_capacity(a_model(), DIFFERENTIAL, HOT, discharge_coefficient=0.0)


def test_a_trap_matched_to_its_load_reads_correct() -> None:
    capacity = condensate_capacity(a_model(), DIFFERENTIAL, HOT)
    load = MassFlow.from_pounds_per_hour(capacity.pounds_per_hour / 3.0)
    check = check_sizing(a_model(), load, DIFFERENTIAL, HOT)
    assert check.verdict is SizingVerdict.CORRECT
    assert not check.verdict.needs_attention
    assert "inside the band" in check.note


def test_a_trap_too_small_for_its_load_reads_undersized() -> None:
    capacity = condensate_capacity(a_model(), DIFFERENTIAL, HOT)
    load = MassFlow.from_pounds_per_hour(capacity.pounds_per_hour)
    check = check_sizing(a_model(), load, DIFFERENTIAL, HOT)
    assert check.verdict is SizingVerdict.UNDERSIZED
    assert "backs up" in check.note
    assert check.verdict.needs_attention


def test_a_trap_far_too_big_reads_oversized() -> None:
    capacity = condensate_capacity(a_model(), DIFFERENTIAL, HOT)
    load = MassFlow.from_pounds_per_hour(capacity.pounds_per_hour / 20.0)
    check = check_sizing(a_model(), load, DIFFERENTIAL, HOT)
    assert check.verdict is SizingVerdict.OVERSIZED
    assert "cuts its own seat" in check.note
    assert check.ratio > OVERSIZE_LIMIT


def test_the_required_flow_carries_the_safety_factor() -> None:
    load = MassFlow.from_pounds_per_hour(100.0)
    check = check_sizing(a_model(), load, DIFFERENTIAL, HOT, safety_factor=3.0)
    assert check.required.pounds_per_hour == pytest.approx(300.0)


def test_a_bigger_safety_factor_can_turn_correct_into_undersized() -> None:
    capacity = condensate_capacity(a_model(), DIFFERENTIAL, HOT)
    load = MassFlow.from_pounds_per_hour(capacity.pounds_per_hour / 3.0)
    assert check_sizing(a_model(), load, DIFFERENTIAL, HOT, safety_factor=2.0).verdict is (
        SizingVerdict.CORRECT
    )
    assert check_sizing(a_model(), load, DIFFERENTIAL, HOT, safety_factor=4.0).verdict is (
        SizingVerdict.UNDERSIZED
    )


def test_a_safety_factor_below_one_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        check_sizing(
            a_model(), MassFlow.from_pounds_per_hour(10.0), DIFFERENTIAL, HOT, safety_factor=0.5
        )


def test_a_leg_with_no_load_at_all_is_infinitely_oversized() -> None:
    check = check_sizing(a_model(), MassFlow.zero(), DIFFERENTIAL, HOT)
    assert check.ratio == float("inf")
    assert check.verdict is SizingVerdict.OVERSIZED


def test_a_smaller_orifice_fixes_an_oversized_station() -> None:
    load = MassFlow.from_pounds_per_hour(30.0)
    big = check_sizing(a_model(orifice=0.186), load, DIFFERENTIAL, HOT)
    small = check_sizing(a_model(orifice=0.031), load, DIFFERENTIAL, HOT)
    assert big.verdict is SizingVerdict.OVERSIZED
    assert small.verdict is SizingVerdict.CORRECT


def test_printing_a_check() -> None:
    load = MassFlow.from_pounds_per_hour(300.0)
    printed = str(check_sizing(replace(a_model(), code="TD52"), load, DIFFERENTIAL, HOT))
    assert printed.startswith("TD52 ")
    assert "passes" in printed
