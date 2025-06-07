from __future__ import annotations

import pytest

from dripleg.diagnosis.combined_rules import (
    COMBINED_RULES,
    GlassCondensate,
    GlassEmpty,
    GlassFlash,
    GlassLiveSteam,
    LoudAndCold,
    QuietAndCold,
    SoundAndHeatAgree,
)
from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.rules import RuleSet
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SightGlassView
from tests.unit.diagnosis.conftest import a_reading, a_station, pipe, probe


def glass(view: SightGlassView) -> DiagnosisContext:
    return DiagnosisContext(a_station(), a_reading(sight_glass=view))


def pair(
    decibels: float,
    cycles: int | None,
    upstream: float,
    downstream: float,
) -> DiagnosisContext:
    return DiagnosisContext(
        a_station(),
        a_reading(ultrasonic=probe(decibels, cycles), temperature=pipe(upstream, downstream)),
    )


def test_live_steam_through_the_glass_settles_it() -> None:
    found = GlassLiveSteam().run(glass(SightGlassView.LIVE_STEAM)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.BLOWING_THROUGH
    assert found[0].is_decisive


def test_condensate_through_the_glass_is_a_pass() -> None:
    found = GlassCondensate().run(glass(SightGlassView.CONDENSATE)).evidence
    assert found[0].supports is TrapCondition.OK
    assert found[0].weight == pytest.approx(0.7)


def test_flash_is_normal_and_carries_less_weight_than_condensate() -> None:
    flash = GlassFlash().run(glass(SightGlassView.FLASH)).evidence
    condensate = GlassCondensate().run(glass(SightGlassView.CONDENSATE)).evidence
    assert flash[0].supports is TrapCondition.OK
    assert flash[0].weight < condensate[0].weight


def test_an_empty_glass_points_at_a_shut_trap() -> None:
    found = GlassEmpty().run(glass(SightGlassView.EMPTY)).evidence
    assert found[0].supports is TrapCondition.FAILED_CLOSED


def test_a_glass_that_cannot_be_seen_skips_every_glass_rule() -> None:
    context = glass(SightGlassView.CANNOT_SEE)
    for rule in (GlassLiveSteam(), GlassCondensate(), GlassFlash(), GlassEmpty()):
        assert rule.run(context).skipped


def test_no_glass_at_all_skips_every_glass_rule() -> None:
    context = DiagnosisContext(a_station(), a_reading())
    for rule in (GlassLiveSteam(), GlassCondensate(), GlassFlash(), GlassEmpty()):
        assert rule.run(context).skipped


def test_each_glass_rule_only_answers_its_own_view() -> None:
    context = glass(SightGlassView.FLASH)
    assert GlassLiveSteam().run(context).evidence == []
    assert GlassCondensate().run(context).evidence == []
    assert GlassEmpty().run(context).evidence == []


def test_a_pair_rule_needs_both_readings() -> None:
    sound_only = DiagnosisContext(a_station(), a_reading(ultrasonic=probe(60.0, 0)))
    heat_only = DiagnosisContext(a_station(), a_reading(temperature=pipe(345.0, 255.0)))
    for rule in (SoundAndHeatAgree(), LoudAndCold(), QuietAndCold()):
        assert rule.run(sound_only).skipped
        assert rule.run(heat_only).skipped


def test_loud_and_hot_downstream_is_the_strong_case() -> None:
    found = SoundAndHeatAgree().run(pair(68.0, 0, 345.0, 255.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.BLOWING_THROUGH
    assert found[0].weight == pytest.approx(0.8)
    assert "both methods agreeing" in found[0].statement


def test_loud_but_a_cool_outlet_does_not_corroborate() -> None:
    assert SoundAndHeatAgree().run(pair(68.0, 0, 345.0, 200.0)).evidence == []


def test_hot_outlet_but_quiet_does_not_corroborate() -> None:
    assert SoundAndHeatAgree().run(pair(20.0, 0, 345.0, 255.0)).evidence == []


def test_a_trap_seen_cycling_does_not_corroborate() -> None:
    assert SoundAndHeatAgree().run(pair(68.0, 3, 345.0, 255.0)).evidence == []


def test_loud_and_cold_together_is_a_blockage() -> None:
    found = LoudAndCold().run(pair(50.0, None, 160.0, 130.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.PLUGGED
    assert found[0].weight == pytest.approx(0.6)


def test_loud_and_hot_is_not_a_blockage() -> None:
    assert LoudAndCold().run(pair(50.0, None, 345.0, 255.0)).evidence == []


def test_quiet_and_cold_is_not_a_blockage() -> None:
    assert LoudAndCold().run(pair(5.0, None, 160.0, 130.0)).evidence == []


def test_quiet_and_cold_together_is_the_strongest_shut_trap_case() -> None:
    found = QuietAndCold().run(pair(5.0, None, 160.0, 130.0)).evidence
    assert len(found) == 1
    assert found[0].supports is TrapCondition.FAILED_CLOSED
    assert found[0].weight == pytest.approx(0.85)


def test_quiet_and_hot_is_not_a_shut_trap() -> None:
    assert QuietAndCold().run(pair(5.0, None, 345.0, 200.0)).evidence == []


def test_the_two_cold_rules_do_not_both_fire() -> None:
    cold = pair(50.0, None, 160.0, 130.0)
    assert LoudAndCold().run(cold).evidence
    assert QuietAndCold().run(cold).evidence == []


def test_the_whole_combined_set_on_a_blowing_trap_with_a_glass() -> None:
    context = DiagnosisContext(
        a_station(),
        a_reading(
            ultrasonic=probe(70.0, 0),
            temperature=pipe(345.0, 258.0),
            sight_glass=SightGlassView.LIVE_STEAM,
        ),
    )
    findings = RuleSet(list(COMBINED_RULES)).run(context)
    assert findings.rules_fired == ["COR-1", "VIS-1"]
    assert findings.weight_for(TrapCondition.BLOWING_THROUGH) == pytest.approx(1.0)


def test_the_combined_rule_codes() -> None:
    assert RuleSet(list(COMBINED_RULES)).codes == [
        "VIS-1",
        "VIS-2",
        "VIS-3",
        "VIS-4",
        "COR-1",
        "COR-2",
        "COR-3",
    ]
