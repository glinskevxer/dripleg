from __future__ import annotations

import pytest

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.coverage import RuleUse, measure_coverage
from dripleg.diagnosis.engine import DEFAULT_RULES
from dripleg.errors import ValidationError
from dripleg.model.tags import TrapTag
from tests.support.build import a_reading, a_station, pipe, probe

BLOWING: dict[str, object] = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY: dict[str, object] = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}


def contexts(readings: list[dict[str, object]]) -> list[DiagnosisContext]:
    out = []
    for index, fields in enumerate(readings, start=1):
        tag = TrapTag.of("B12", "MP", index)
        out.append(
            DiagnosisContext(
                a_station(tag=tag),
                a_reading(tag=tag, **fields),
            )
        )
    return out


def test_a_use_counts_what_it_saw() -> None:
    use = RuleUse("SND-1", "a rule", skipped=3, silent=4, fired=3)
    assert use.seen == 10
    assert use.applied == 7
    assert use.fire_rate == pytest.approx(3 / 7)


def test_a_negative_count_is_refused() -> None:
    with pytest.raises(ValidationError, match="not negative"):
        RuleUse("SND-1", "a rule", skipped=-1, silent=0, fired=0)


def test_a_rule_that_never_fires_is_dead() -> None:
    assert RuleUse("SND-1", "a rule", skipped=0, silent=5, fired=0).is_dead
    assert not RuleUse("SND-1", "a rule", skipped=0, silent=4, fired=1).is_dead


def test_a_rule_that_is_never_applied_says_so() -> None:
    use = RuleUse("SND-1", "a rule", skipped=9, silent=0, fired=0)
    assert use.is_never_applied
    assert use.is_dead
    assert use.fire_rate == 0.0
    assert "the reading is not taken" in str(use)


def test_a_rule_that_fires_on_everything_separates_nothing() -> None:
    assert RuleUse("SND-1", "a rule", skipped=0, silent=0, fired=5).separates_nothing
    assert not RuleUse("SND-1", "a rule", skipped=0, silent=0, fired=4).separates_nothing


def test_the_whole_set_is_measured_over_a_batch() -> None:
    coverage = measure_coverage(DEFAULT_RULES, contexts([BLOWING, HEALTHY, HEALTHY]))
    assert coverage.readings == 3
    assert len(coverage.uses) == len(DEFAULT_RULES)


def test_every_rule_saw_every_reading() -> None:
    coverage = measure_coverage(DEFAULT_RULES, contexts([BLOWING, HEALTHY]))
    assert all(use.seen == 2 for use in coverage.uses)


def test_the_sound_rules_fire_on_a_blowing_trap() -> None:
    coverage = measure_coverage(DEFAULT_RULES, contexts([BLOWING]))
    blow = coverage.find("snd-1")
    assert blow is not None
    assert blow.fired == 1


def test_the_glass_rules_are_never_applied_without_a_glass() -> None:
    coverage = measure_coverage(DEFAULT_RULES, contexts([BLOWING, HEALTHY]))
    glass = coverage.find("VIS-1")
    assert glass is not None
    assert glass.is_never_applied
    assert glass in coverage.never_applied


def test_the_working_rules_are_the_ones_that_fired() -> None:
    coverage = measure_coverage(DEFAULT_RULES, contexts([BLOWING, HEALTHY, HEALTHY]))
    assert coverage.working
    assert all(use.fired > 0 for use in coverage.working)


def test_a_rule_nobody_named() -> None:
    coverage = measure_coverage(DEFAULT_RULES, contexts([BLOWING]))
    assert coverage.find("ZZZ-9") is None


def test_an_empty_batch_leaves_every_rule_unseen() -> None:
    coverage = measure_coverage(DEFAULT_RULES, [])
    assert coverage.readings == 0
    assert all(use.seen == 0 for use in coverage.uses)
    assert coverage.dead == []
    assert coverage.never_applied == []


def test_printing_a_use_and_a_coverage() -> None:
    use = RuleUse("SND-1", "a rule", skipped=1, silent=1, fired=2)
    assert str(use) == "SND-1: fired on 2 of 3 (67%), skipped 1"
    coverage = measure_coverage(DEFAULT_RULES, contexts([BLOWING]))
    assert str(coverage).startswith(f"{len(DEFAULT_RULES)} rules over 1 readings")
