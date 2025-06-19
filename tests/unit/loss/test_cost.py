from __future__ import annotations

from decimal import Decimal

import pytest

from dripleg.errors import ValidationError
from dripleg.loss.cost import POUNDS_PER_GALLON, CostBasis, LossCost
from dripleg.loss.energy import EnergyModel
from dripleg.loss.estimate import estimate_steam_loss
from dripleg.model.header import DischargeDestination
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money, Price
from tests.unit.diagnosis.conftest import a_header, a_station


def cost_of(condition: TrapCondition = TrapCondition.BLOWING_THROUGH, **kwargs: object) -> LossCost:
    station = a_station(**kwargs)
    loss = estimate_steam_loss(station, condition)
    heat = EnergyModel.typical().assess(station, loss)
    return CostBasis.typical().cost_of(heat)


def test_the_typical_basis_is_priced_per_mmbtu_and_per_thousand_gallons() -> None:
    basis = CostBasis.typical()
    assert basis.fuel.unit == "MMBtu"
    assert basis.water.unit == "1000 gal"


def test_fuel_has_to_be_priced_per_mmbtu() -> None:
    with pytest.raises(ValidationError, match="per MMBtu"):
        CostBasis(
            fuel=Price.of("6.25", "therm"),
            water=Price.of("4.10", "1000 gal"),
            effluent=Price.of("3.40", "1000 gal"),
            chemical=Price.of("2.75", "1000 gal"),
        )


def test_the_water_prices_have_to_be_per_gallon() -> None:
    with pytest.raises(ValidationError, match="per thousand gallons"):
        CostBasis(
            fuel=Price.of("6.25", "MMBtu"),
            water=Price.of("4.10", "litre"),
            effluent=Price.of("3.40", "1000 gal"),
            chemical=Price.of("2.75", "1000 gal"),
        )


def test_a_healthy_trap_costs_nothing() -> None:
    cost = cost_of(TrapCondition.OK)
    assert cost.is_free
    assert cost.total == Money.zero()
    assert cost.fuel_share == 0.0


def test_a_blowing_trap_costs_thousands_a_year() -> None:
    cost = cost_of()
    assert cost.total.dollars > Decimal("500.00")
    assert not cost.is_free


def test_fuel_is_most_of_the_bill_but_not_all_of_it() -> None:
    cost = cost_of()
    assert 0.75 < cost.fuel_share < 1.0
    assert cost.water_side.cents > 0


def test_the_water_side_is_three_charges() -> None:
    cost = cost_of()
    assert cost.water_side == cost.water + cost.effluent + cost.chemical
    assert cost.water.cents > 0
    assert cost.effluent.cents > 0
    assert cost.chemical.cents > 0


def test_a_vented_trap_costs_more_water_than_a_returned_one() -> None:
    vented = cost_of(header=a_header(discharge=0.0, destination=DischargeDestination.ATMOSPHERE))
    returned = cost_of()
    assert vented.water.cents > returned.water.cents
    assert vented.total.cents > returned.total.cents


def test_a_leaking_trap_costs_less_than_a_blowing_one() -> None:
    assert cost_of(TrapCondition.LEAKING).total.cents < cost_of().total.cents


def test_the_fuel_line_follows_the_fuel_price() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    heat = EnergyModel.typical().assess(station, loss)
    cheap = CostBasis(
        fuel=Price.of("3.00", "MMBtu"),
        water=Price.of("4.10", "1000 gal"),
        effluent=Price.of("3.40", "1000 gal"),
        chemical=Price.of("2.75", "1000 gal"),
    ).cost_of(heat)
    dear = CostBasis(
        fuel=Price.of("9.00", "MMBtu"),
        water=Price.of("4.10", "1000 gal"),
        effluent=Price.of("3.40", "1000 gal"),
        chemical=Price.of("2.75", "1000 gal"),
    ).cost_of(heat)
    assert dear.fuel.cents == pytest.approx(cheap.fuel.cents * 3, rel=0.001)
    assert dear.water == cheap.water


def test_the_water_charge_follows_the_makeup_volume() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    heat = EnergyModel.typical().assess(station, loss)
    gallons = heat.makeup_water.pounds / POUNDS_PER_GALLON
    expected = Money.from_dollars(Decimal(str(gallons / 1000.0)) * Decimal("4.10"))
    assert CostBasis.typical().cost_of(heat).water == expected


def test_the_lines_add_up_to_the_total() -> None:
    cost = cost_of()
    lines = dict(cost.lines())
    assert (
        lines["fuel"] + lines["makeup water"] + lines["effluent"] + lines["treatment chemical"]
        == lines["total"]
    )
    assert [name for name, _ in cost.lines()][-1] == "total"


def test_the_cost_knows_which_trap_it_is() -> None:
    cost = cost_of()
    assert cost.tag == "B12-MP-0043"
    assert str(cost).startswith("B12-MP-0043 $")
    assert str(cost).endswith(" a year")
