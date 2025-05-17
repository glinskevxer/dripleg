from __future__ import annotations

import pytest

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.rules import RuleSet
from dripleg.diagnosis.sound_rules import (
    SOUND_RULES,
    CycleRateHigh,
    HealthyCycling,
    LevelBlowThrough,
    LevelLeaking,
    NoCyclesOnCyclingTrap,
    Silent,
    sound_bands,
)
from dripleg.model.header import PressureClass
from dripleg.model.principles import OperatingPrinciple
from dripleg.survey.condition import TrapCondition
from tests.unit.diagnosis.conftest import a_header, a_model, a_reading, a_station, probe


def context(
    decibels: float | None = None,
    cycles: int | None = None,
    *,
    seconds: float = 30.0,
    principle: OperatingPrinciple = OperatingPrinciple.THERMODYNAMIC_DISC,
    header_psig: float = 125.0,
) -> DiagnosisContext:
    sound = None if decibels is None else probe(decibels, cycles, seconds)
    return DiagnosisContext(
        a_station(
            model=a_model(principle),
            header=a_header(operating=header_psig, discharge=min(15.0, header_psig / 4.0)),
        ),
        a_reading(ultrasonic=sound),
    )


def test_the_bands_climb_with_pressure() -> None:
    low = sound_bands(context(header_psig=10.0))
    medium = sound_bands(context(header_psig=125.0))
    high = sound_bands(context(header_psig=250.0))
    assert low < medium < high
    assert PressureClass.of(context(header_psig=250.0).pressure) is PressureClass.HIGH


def test_every_band_runs_quiet_to_leak_to_blow() -> None:
    for pressure in (5.0, 30.0, 125.0, 400.0):
        quiet, leak, blow = sound_bands(context(header_psig=pressure))
        assert quiet < leak < blow


def test_no_sound_rule_applies_without_a_probe() -> None:
    bare = DiagnosisContext(a_station(), a_reading())
    assert RuleSet(list(SOUND_RULES)).applicable_to(bare) == []


def test_a_loud_steady_disc_trap_reads_as_blowing_through() -> None:
    found = LevelBlowThrough().run(context(68.0, cycles=0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.BLOWING_THROUGH
    assert found[0].weight == pytest.approx(0.75)
    assert "68 dB steady" in found[0].statement


def test_a_loud_reading_with_no_count_still_counts() -> None:
    found = LevelBlowThrough().run(context(68.0)).evidence
    assert len(found) == 1


def test_a_loud_trap_that_was_seen_to_cycle_is_not_blowing_through() -> None:
    assert LevelBlowThrough().run(context(68.0, cycles=3)).evidence == []


def test_a_continuous_trap_gets_a_softer_verdict_on_level_alone() -> None:
    disc = LevelBlowThrough().run(context(68.0, cycles=0)).evidence[0]
    float_trap = (
        LevelBlowThrough()
        .run(context(68.0, cycles=0, principle=OperatingPrinciple.FLOAT_THERMOSTATIC))
        .evidence[0]
    )
    assert float_trap.weight < disc.weight


def test_the_blow_through_floor_moves_with_pressure() -> None:
    assert LevelBlowThrough().run(context(48.0, cycles=0, header_psig=10.0)).evidence
    assert not LevelBlowThrough().run(context(48.0, cycles=0, header_psig=125.0)).evidence


def test_a_middling_level_reads_as_leaking() -> None:
    found = LevelLeaking().run(context(44.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.LEAKING


def test_a_level_below_the_leak_floor_says_nothing() -> None:
    assert LevelLeaking().run(context(20.0)).evidence == []


def test_a_level_above_the_blow_floor_is_not_a_leak() -> None:
    assert LevelLeaking().run(context(68.0)).evidence == []


def test_silence_points_at_a_trap_that_is_not_passing() -> None:
    found = Silent().run(context(4.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.FAILED_CLOSED
    assert Silent().run(context(30.0)).evidence == []


def test_cycling_far_too_fast() -> None:
    found = CycleRateHigh().run(context(40.0, cycles=8)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.RAPID_CYCLING
    assert found[0].weight == pytest.approx(0.5)


def test_cycling_at_double_the_ceiling_weighs_more() -> None:
    found = CycleRateHigh().run(context(40.0, cycles=10)).evidence
    assert found[0].weight == pytest.approx(0.7)


def test_cycling_inside_the_band_is_not_rapid() -> None:
    assert CycleRateHigh().run(context(40.0, cycles=2)).evidence == []


def test_the_cycle_rule_needs_a_count() -> None:
    assert CycleRateHigh().run(context(40.0)).skipped


def test_an_intermittent_trap_with_no_discharges_is_a_finding() -> None:
    found = NoCyclesOnCyclingTrap().run(context(50.0, cycles=0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.BLOWING_THROUGH
    assert "no discharges counted" in found[0].statement


def test_a_continuous_trap_with_no_discharges_is_normal() -> None:
    outcome = NoCyclesOnCyclingTrap().run(
        context(50.0, cycles=0, principle=OperatingPrinciple.FLOAT_THERMOSTATIC)
    )
    assert outcome.skipped


def test_a_silent_intermittent_trap_is_not_this_rule() -> None:
    assert NoCyclesOnCyclingTrap().run(context(2.0, cycles=0)).evidence == []


def test_a_healthy_cycling_trap_gets_a_pass() -> None:
    found = HealthyCycling().run(context(35.0, cycles=2)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.OK


def test_a_loud_cycling_trap_gets_no_pass() -> None:
    assert HealthyCycling().run(context(68.0, cycles=2)).evidence == []


def test_a_slow_cycling_disc_trap_gets_no_pass() -> None:
    assert HealthyCycling().run(context(35.0, cycles=0, seconds=60.0)).evidence == []


def test_the_pass_rule_does_not_apply_to_a_continuous_trap() -> None:
    outcome = HealthyCycling().run(
        context(35.0, cycles=0, principle=OperatingPrinciple.FLOAT_THERMOSTATIC)
    )
    assert outcome.skipped


def test_the_whole_sound_set_on_a_blowing_disc_trap() -> None:
    findings = RuleSet(list(SOUND_RULES)).run(context(70.0, cycles=0))
    assert findings.weight_for(TrapCondition.BLOWING_THROUGH) > 0.9
    assert findings.weight_for(TrapCondition.OK) == 0.0
    assert set(findings.rules_fired) == {"SND-1", "SND-5"}


def test_the_whole_sound_set_on_a_healthy_disc_trap() -> None:
    findings = RuleSet(list(SOUND_RULES)).run(context(32.0, cycles=2))
    assert findings.conditions() == [TrapCondition.OK]
    assert findings.rules_fired == ["SND-6"]


def test_the_rule_codes_are_unique_and_in_order() -> None:
    assert RuleSet(list(SOUND_RULES)).codes == [
        "SND-1",
        "SND-2",
        "SND-3",
        "SND-4",
        "SND-5",
        "SND-6",
    ]
