from __future__ import annotations

import pytest

from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.sensitivity import Sensitivity, sweep
from dripleg.model.operating import OperatingProfile, ServicePattern
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money
from tests.support.build import a_station


def a_sweep(condition: TrapCondition = TrapCondition.LEAKING, **station: object) -> Sensitivity:
    return sweep(
        a_station(**station),
        condition,
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )


def test_a_healthy_trap_has_nothing_to_sweep() -> None:
    result = a_sweep(TrapCondition.OK)
    assert result.swings == []
    assert result.base_cost == Money.zero()
    assert result.worst is None
    assert result.widest_share == 0.0


def test_every_assumption_is_swept() -> None:
    names = {swing.assumption for swing in a_sweep().swings}
    assert names == {
        "open fraction of the seat",
        "live hours a year",
        "boiler efficiency",
        "condensate returned",
        "fuel price",
    }


def test_the_swings_come_back_widest_first() -> None:
    shares = [swing.share_of_base for swing in a_sweep().swings]
    assert shares == sorted(shares, reverse=True)


def test_the_open_fraction_is_the_widest_on_a_leaking_trap() -> None:
    result = a_sweep(TrapCondition.LEAKING)
    assert result.worst is not None
    assert result.worst.assumption == "open fraction of the seat"
    assert result.worst.share_of_base > 1.0


def test_a_blowing_trap_cannot_open_any_further() -> None:
    result = a_sweep(TrapCondition.BLOWING_THROUGH)
    swing = result.named("open fraction of the seat")
    assert swing is not None
    assert swing.high_cost == result.base_cost


def test_the_hours_swing_is_nothing_on_a_continuous_leg() -> None:
    swing = a_sweep().named("live hours a year")
    assert swing is not None
    assert swing.high_cost == swing.base_cost
    assert swing.low_cost.cents == pytest.approx(swing.base_cost.cents / 2, rel=0.01)


def test_the_hours_swing_is_wide_on_a_seasonal_leg() -> None:
    heating = OperatingProfile("HEAT", "Heating", ServicePattern.HEATING_SEASON)
    swing = a_sweep(profile=heating).named("live hours a year")
    assert swing is not None
    assert swing.high_cost.cents > swing.base_cost.cents


def test_a_worse_boiler_costs_more() -> None:
    swing = a_sweep().named("boiler efficiency")
    assert swing is not None
    assert swing.high_cost.cents > swing.low_cost.cents


def test_losing_all_the_condensate_costs_more() -> None:
    swing = a_sweep().named("condensate returned")
    assert swing is not None
    assert swing.high_cost.cents > swing.low_cost.cents


def test_the_fuel_price_swing_is_a_straight_double() -> None:
    swing = a_sweep().named("fuel price")
    assert swing is not None
    assert swing.high_cost.cents == pytest.approx(swing.base_cost.cents * 2, rel=0.001)
    assert swing.share_of_base == pytest.approx(1.5, rel=0.001)


def test_an_assumption_nobody_sweeps() -> None:
    assert a_sweep().named("the phase of the moon") is None


def test_the_spread_is_the_gap_between_the_ends() -> None:
    swing = a_sweep().named("fuel price")
    assert swing is not None
    assert swing.spread == swing.high_cost - swing.low_cost


def test_printing_a_swing_and_a_sweep() -> None:
    result = a_sweep()
    assert str(result).startswith("B12-MP-0043 at $")
    assert "most sensitive to" in str(result)
    assert str(a_sweep(TrapCondition.OK)).endswith("nothing moves it")
    swing = result.swings[0]
    assert str(swing).startswith(swing.assumption)
