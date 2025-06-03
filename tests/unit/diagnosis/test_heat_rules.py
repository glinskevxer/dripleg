from __future__ import annotations

import pytest

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.heat_rules import (
    HEAT_RULES,
    ColdInlet,
    ExcessSubcooling,
    HealthyDrop,
    HotOutlet,
    WholeTrapCold,
    expected_outlet,
)
from dripleg.diagnosis.rules import RuleSet
from dripleg.model.header import DischargeDestination
from dripleg.model.principles import OperatingPrinciple
from dripleg.survey.condition import TrapCondition
from tests.unit.diagnosis.conftest import a_header, a_model, a_reading, a_station, pipe


def context(
    upstream: float,
    downstream: float,
    ambient: float | None = None,
    *,
    principle: OperatingPrinciple = OperatingPrinciple.THERMODYNAMIC_DISC,
    header_psig: float = 125.0,
    discharge_psig: float = 15.0,
    destination: DischargeDestination = DischargeDestination.RETURN_LINE,
) -> DiagnosisContext:
    return DiagnosisContext(
        a_station(
            model=a_model(principle),
            header=a_header(
                operating=header_psig, discharge=discharge_psig, destination=destination
            ),
        ),
        a_reading(temperature=pipe(upstream, downstream, ambient)),
    )


def test_the_expected_outlet_is_saturation_in_the_return_line() -> None:
    assert expected_outlet(context(340.0, 210.0)).fahrenheit == pytest.approx(250.0, abs=2.0)
    vented = context(340.0, 210.0, discharge_psig=0.0, destination=DischargeDestination.ATMOSPHERE)
    assert expected_outlet(vented).fahrenheit == pytest.approx(212.0, abs=1.0)


def test_no_heat_rule_applies_without_a_temperature_reading() -> None:
    bare = DiagnosisContext(a_station(), a_reading())
    assert RuleSet(list(HEAT_RULES)).applicable_to(bare) == []


def test_an_outlet_at_return_saturation_is_steam_of_some_kind() -> None:
    found = HotOutlet().run(context(345.0, 252.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.BLOWING_THROUGH
    assert "flash and live steam share" in found[0].statement


def test_the_hot_outlet_rule_is_deliberately_weak() -> None:
    found = HotOutlet().run(context(345.0, 252.0)).evidence
    assert found[0].weight < 0.4


def test_a_cool_outlet_says_nothing() -> None:
    assert HotOutlet().run(context(345.0, 200.0)).evidence == []


def test_a_hot_outlet_on_a_cold_trap_is_not_reported_twice() -> None:
    assert HotOutlet().run(context(150.0, 260.0)).evidence == []


def test_a_vented_trap_has_a_lower_outlet_threshold() -> None:
    vented = context(345.0, 214.0, discharge_psig=0.0, destination=DischargeDestination.ATMOSPHERE)
    assert HotOutlet().run(vented).evidence
    assert HotOutlet().run(context(345.0, 214.0)).evidence == []


def test_a_cold_inlet_points_at_a_trap_that_is_not_passing() -> None:
    found = ColdInlet().run(context(160.0, 120.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.FAILED_CLOSED
    assert found[0].weight == pytest.approx(0.65)


def test_a_thermostatic_trap_gets_the_benefit_of_the_doubt() -> None:
    found = ColdInlet().run(context(160.0, 120.0, principle=OperatingPrinciple.BIMETALLIC)).evidence
    assert found[0].weight == pytest.approx(0.45)


def test_a_warm_inlet_is_not_a_cold_trap() -> None:
    assert ColdInlet().run(context(345.0, 210.0)).evidence == []


def test_a_trap_at_air_temperature_is_out_of_service() -> None:
    found = WholeTrapCold().run(context(90.0, 85.0, ambient=72.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.OUT_OF_SERVICE
    assert found[0].weight == pytest.approx(0.7)


def test_a_hot_trap_with_an_ambient_reading_is_not_out_of_service() -> None:
    assert WholeTrapCold().run(context(345.0, 210.0, ambient=72.0)).evidence == []


def test_the_out_of_service_rule_needs_an_ambient_reading() -> None:
    assert WholeTrapCold().run(context(90.0, 85.0)).skipped


def test_subcooling_past_the_principle_band_looks_like_a_plugged_strainer() -> None:
    found = ExcessSubcooling().run(context(300.0, 200.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.PLUGGED


def test_the_same_reading_on_a_thermostatic_trap_is_normal() -> None:
    warm = context(300.0, 200.0, principle=OperatingPrinciple.BIMETALLIC)
    assert ExcessSubcooling().run(warm).evidence == []


def test_a_cold_trap_is_not_also_reported_as_slightly_cool() -> None:
    assert ExcessSubcooling().run(context(160.0, 120.0)).evidence == []


def test_an_inlet_above_saturation_is_not_subcooled_at_all() -> None:
    assert ExcessSubcooling().run(context(380.0, 200.0)).evidence == []


def test_a_hot_inlet_and_a_cool_outlet_is_a_pass() -> None:
    found = HealthyDrop().run(context(350.0, 200.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.OK
    assert "150 F across the trap" in found[0].statement


def test_a_hot_outlet_is_not_a_pass() -> None:
    assert HealthyDrop().run(context(350.0, 255.0)).evidence == []


def test_a_cold_inlet_is_not_a_pass() -> None:
    assert HealthyDrop().run(context(160.0, 120.0)).evidence == []


def test_the_whole_heat_set_on_a_healthy_trap() -> None:
    findings = RuleSet(list(HEAT_RULES)).run(context(350.0, 200.0, ambient=72.0))
    assert findings.conditions() == [TrapCondition.OK]
    assert findings.rules_fired == ["TMP-5"]


def test_the_whole_heat_set_on_a_cold_trap() -> None:
    findings = RuleSet(list(HEAT_RULES)).run(context(150.0, 130.0, ambient=72.0))
    assert findings.weight_for(TrapCondition.FAILED_CLOSED) == pytest.approx(0.65)
    assert findings.weight_for(TrapCondition.OK) == 0.0


def test_the_whole_heat_set_on_a_trap_with_a_hot_outlet() -> None:
    findings = RuleSet(list(HEAT_RULES)).run(context(348.0, 260.0))
    assert findings.conditions() == [TrapCondition.BLOWING_THROUGH]
    assert findings.weight_for(TrapCondition.BLOWING_THROUGH) < 0.5


def test_the_heat_rule_codes() -> None:
    assert RuleSet(list(HEAT_RULES)).codes == ["TMP-1", "TMP-2", "TMP-3", "TMP-4", "TMP-5"]
