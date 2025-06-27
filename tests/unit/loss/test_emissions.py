from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.loss.emissions import FACTORS, EmissionsFactor, StackLoss, factor_named
from dripleg.loss.energy import EnergyModel
from dripleg.loss.estimate import estimate_steam_loss
from dripleg.survey.condition import TrapCondition
from dripleg.units.energy import Energy
from tests.support.build import a_station


def heat_loss(condition: TrapCondition = TrapCondition.BLOWING_THROUGH):  # type: ignore[no-untyped-def]
    station = a_station()
    return EnergyModel.typical().assess(station, estimate_steam_loss(station, condition))


def test_every_published_factor_is_sane() -> None:
    for factor in FACTORS.values():
        assert factor.kg_co2e_per_mmbtu > 0
        assert factor.source.strip()
        assert factor.name.strip()


def test_the_factors_rank_the_way_fuels_do() -> None:
    assert FACTORS["coal"].kg_co2e_per_mmbtu > FACTORS["fuel_oil_2"].kg_co2e_per_mmbtu
    assert FACTORS["fuel_oil_2"].kg_co2e_per_mmbtu > FACTORS["natural_gas"].kg_co2e_per_mmbtu
    assert FACTORS["biomass"].kg_co2e_per_mmbtu < FACTORS["natural_gas"].kg_co2e_per_mmbtu


def test_a_factor_is_checked_when_it_is_built() -> None:
    with pytest.raises(ValidationError, match="needs a name"):
        EmissionsFactor(" ", 53.1, "somewhere", dt.date(2024, 4, 1))
    with pytest.raises(ValidationError, match="is positive"):
        EmissionsFactor("gas", 0.0, "somewhere", dt.date(2024, 4, 1))
    with pytest.raises(ValidationError, match="where the factor came from"):
        EmissionsFactor("gas", 53.1, "  ", dt.date(2024, 4, 1))


def test_applying_a_factor_gives_tonnes() -> None:
    factor = FACTORS["natural_gas"]
    assert factor.applied_to(Energy.from_mmbtu(1000.0)) == pytest.approx(53.1)
    assert factor.applied_to(Energy.zero()) == pytest.approx(0.0)


def test_an_old_factor_is_flagged_as_stale() -> None:
    old = EmissionsFactor("gas", 53.1, "an old book", dt.date(2010, 1, 1))
    fresh = EmissionsFactor("gas", 53.1, "this year", dt.date.today())
    assert old.is_stale
    assert not fresh.is_stale


def test_looking_a_factor_up_by_name() -> None:
    assert factor_named("natural gas") is FACTORS["natural_gas"]
    assert factor_named("FUEL-OIL-2") is FACTORS["fuel_oil_2"]


def test_a_fuel_with_no_factor_says_what_there_is() -> None:
    with pytest.raises(ValidationError, match="expected one of: biomass"):
        factor_named("hydrogen")


def test_a_blowing_trap_is_material_in_a_carbon_report() -> None:
    stack = StackLoss(heat=heat_loss(), factor=FACTORS["natural_gas"])
    assert stack.tonnes_co2e > 5.0
    assert stack.is_material
    assert stack.kilograms_co2e == pytest.approx(stack.tonnes_co2e * 1000.0)


def test_a_healthy_trap_emits_nothing() -> None:
    stack = StackLoss(heat=heat_loss(TrapCondition.OK), factor=FACTORS["natural_gas"])
    assert stack.tonnes_co2e == pytest.approx(0.0)
    assert not stack.is_material


def test_the_fuel_changes_the_answer_and_not_the_loss() -> None:
    heat = heat_loss()
    gas = StackLoss(heat=heat, factor=FACTORS["natural_gas"])
    coal = StackLoss(heat=heat, factor=FACTORS["coal"])
    assert coal.tonnes_co2e > gas.tonnes_co2e
    ratio = FACTORS["coal"].kg_co2e_per_mmbtu / FACTORS["natural_gas"].kg_co2e_per_mmbtu
    assert coal.tonnes_co2e == pytest.approx(gas.tonnes_co2e * ratio)


def test_a_leaking_trap_emits_less_than_a_blowing_one() -> None:
    blowing = StackLoss(heat=heat_loss(), factor=FACTORS["natural_gas"])
    leaking = StackLoss(heat=heat_loss(TrapCondition.LEAKING), factor=FACTORS["natural_gas"])
    assert leaking.tonnes_co2e < blowing.tonnes_co2e


def test_printing_a_factor_and_a_stack_loss() -> None:
    assert str(FACTORS["natural_gas"]) == "natural gas 53.1 kg/MMBtu (2024-04-01)"
    printed = str(StackLoss(heat=heat_loss(), factor=FACTORS["natural_gas"]))
    assert printed.startswith("B12-MP-0043 ")
    assert "t CO2e a year on the natural gas factor" in printed
