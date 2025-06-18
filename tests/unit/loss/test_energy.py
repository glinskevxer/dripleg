from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.loss.energy import EnergyModel
from dripleg.loss.estimate import estimate_steam_loss
from dripleg.model.header import DischargeDestination
from dripleg.model.installation import TrapInstallation
from dripleg.survey.condition import TrapCondition
from dripleg.units.temperature import Temperature
from tests.unit.diagnosis.conftest import a_header, a_station


def a_model(**overrides: object) -> EnergyModel:
    fields: dict[str, object] = {
        "feedwater_temperature": Temperature.from_fahrenheit(227.0),
        "boiler_efficiency": 0.82,
        "condensate_returned": 0.75,
        "receiver_vent_fraction": 0.35,
    }
    fields.update(overrides)
    return EnergyModel(**fields)  # type: ignore[arg-type]


def vented_station() -> TrapInstallation:
    return a_station(header=a_header(discharge=0.0, destination=DischargeDestination.ATMOSPHERE))


def test_the_typical_model_is_a_deaerator_at_227() -> None:
    model = EnergyModel.typical()
    assert model.feedwater_temperature.fahrenheit == pytest.approx(227.0)
    assert model.feedwater_enthalpy().btu_per_pound == pytest.approx(195.0)


def test_the_model_checks_its_fractions() -> None:
    with pytest.raises(ValidationError, match="boiler efficiency"):
        a_model(boiler_efficiency=0.0)
    with pytest.raises(ValidationError, match="returned condensate fraction"):
        a_model(condensate_returned=1.4)
    with pytest.raises(ValidationError, match="receiver vent fraction"):
        a_model(receiver_vent_fraction=-0.1)


def test_a_vented_trap_loses_the_whole_enthalpy() -> None:
    station = vented_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    per_pound = a_model().heat_per_pound(station, loss)
    assert per_pound.btu_per_pound == pytest.approx(1193.0 - 195.0, abs=6.0)


def test_a_closed_return_is_cheaper_but_not_much() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    returned = a_model().heat_per_pound(station, loss).btu_per_pound
    vented_loss = estimate_steam_loss(vented_station(), TrapCondition.BLOWING_THROUGH)
    vented = a_model().heat_per_pound(vented_station(), vented_loss).btu_per_pound
    assert returned < vented
    assert returned > vented * 0.85


def test_returning_every_pound_of_condensate_is_the_best_case() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    good = a_model(condensate_returned=1.0, receiver_vent_fraction=0.0)
    poor = a_model(condensate_returned=0.0, receiver_vent_fraction=0.0)
    assert good.heat_per_pound(station, loss) < poor.heat_per_pound(station, loss)


def test_a_receiver_that_vents_everything_is_the_same_as_an_open_discharge() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    all_vented = a_model(receiver_vent_fraction=1.0).heat_per_pound(station, loss)
    vented_loss = estimate_steam_loss(vented_station(), TrapCondition.BLOWING_THROUGH)
    open_line = a_model().heat_per_pound(vented_station(), vented_loss)
    assert all_vented.btu_per_pound == pytest.approx(open_line.btu_per_pound, abs=1.0)


def test_hotter_feedwater_means_less_heat_to_replace() -> None:
    station = vented_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    cold = a_model(feedwater_temperature=Temperature.from_fahrenheit(60.0))
    hot = a_model(feedwater_temperature=Temperature.from_fahrenheit(240.0))
    assert hot.heat_per_pound(station, loss) < cold.heat_per_pound(station, loss)


def test_a_vented_trap_needs_a_pound_of_makeup_per_pound_of_steam() -> None:
    assert a_model().water_lost_per_pound(vented_station()) == pytest.approx(1.0)


def test_a_closed_return_needs_less_makeup() -> None:
    water = a_model().water_lost_per_pound(a_station())
    assert water == pytest.approx(1.0 - 0.65 * 0.75)
    assert 0.0 < water < 1.0


def test_a_perfect_return_needs_no_makeup() -> None:
    perfect = a_model(condensate_returned=1.0, receiver_vent_fraction=0.0)
    assert perfect.water_lost_per_pound(a_station()) == pytest.approx(0.0)


def test_the_assessment_carries_the_annual_numbers() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    heat = a_model().assess(station, loss)
    assert heat.annual_heat.btu == pytest.approx(
        heat.heat_per_pound.btu_per_pound * loss.pounds_per_year
    )
    assert heat.annual_fuel.btu == pytest.approx(heat.annual_heat.btu / 0.82)
    assert heat.mmbtu_per_year > 100.0
    assert heat.recovered


def test_a_worse_boiler_burns_more_fuel_for_the_same_loss() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    good = a_model(boiler_efficiency=0.90).assess(station, loss)
    poor = a_model(boiler_efficiency=0.70).assess(station, loss)
    assert poor.mmbtu_per_year > good.mmbtu_per_year
    assert poor.annual_heat.btu == pytest.approx(good.annual_heat.btu)


def test_a_healthy_trap_assesses_to_nothing() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.OK)
    heat = a_model().assess(station, loss)
    assert heat.annual_heat.btu == pytest.approx(0.0)
    assert heat.makeup_water.pounds == pytest.approx(0.0)


def test_the_destination_note_says_which_case_it_is() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    assert "closed return" in a_model().assess(station, loss).destination_note
    vented = vented_station()
    vented_loss = estimate_steam_loss(vented, TrapCondition.BLOWING_THROUGH)
    assert "atmosphere" in a_model().assess(vented, vented_loss).destination_note


def test_printing_a_heat_loss() -> None:
    station = a_station()
    loss = estimate_steam_loss(station, TrapCondition.BLOWING_THROUGH)
    printed = str(a_model().assess(station, loss))
    assert printed.startswith("B12-MP-0043 ")
    assert "MMBtu of fuel a year" in printed
    assert "lb of makeup" in printed
