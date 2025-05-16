from __future__ import annotations

import pytest

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.evidence import Evidence
from dripleg.diagnosis.rules import Rule, RuleSet
from dripleg.errors import ConflictError, NotFoundError, ValidationError
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SurveyMethod
from tests.unit.diagnosis.conftest import a_reading, a_station, probe


class NeedsSound(Rule):
    code = "TST-1"
    description = "fires when there is an ultrasonic reading"
    method = SurveyMethod.ULTRASONIC

    def applies_to(self, context: DiagnosisContext) -> bool:
        return context.has_sound

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        assert context.sound is not None
        return [
            Evidence(
                rule=self.code,
                statement=f"{context.sound.decibels:.0f} dB",
                supports=TrapCondition.LEAKING,
                weight=0.4,
                method=self.method,
            )
        ]


class AlwaysQuiet(Rule):
    code = "TST-2"
    description = "applies to everything and never finds anything"

    def applies_to(self, context: DiagnosisContext) -> bool:
        return True

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        return []


class Mislabelled(Rule):
    code = "TST-3"
    description = "produces evidence under somebody else's code"

    def applies_to(self, context: DiagnosisContext) -> bool:
        return True

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        return [
            Evidence(
                rule="OTHER",
                statement="not mine",
                supports=TrapCondition.OK,
                weight=0.5,
                method=SurveyMethod.VISUAL,
            )
        ]


class Nameless(Rule):
    description = "has no code"

    def applies_to(self, context: DiagnosisContext) -> bool:
        return True

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        return []


class Undescribed(Rule):
    code = "TST-4"

    def applies_to(self, context: DiagnosisContext) -> bool:
        return True

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        return []


def quiet_context() -> DiagnosisContext:
    return DiagnosisContext(a_station(), a_reading())


def loud_context() -> DiagnosisContext:
    return DiagnosisContext(a_station(), a_reading(ultrasonic=probe(58.0, cycles=0)))


def test_a_rule_without_a_code_or_a_description_is_refused() -> None:
    with pytest.raises(ValidationError, match="no rule code"):
        Nameless()
    with pytest.raises(ValidationError, match="no description"):
        Undescribed()


def test_a_rule_that_does_not_apply_is_skipped_not_passed() -> None:
    outcome = NeedsSound().run(quiet_context())
    assert outcome.skipped
    assert not outcome.fired
    assert not outcome.looked_and_found_nothing
    assert str(outcome) == "TST-1 skipped"


def test_a_rule_that_applies_and_finds_something() -> None:
    outcome = NeedsSound().run(loud_context())
    assert not outcome.skipped
    assert outcome.fired
    assert outcome.evidence[0].statement == "58 dB"
    assert str(outcome) == "TST-1 produced 1"


def test_a_rule_that_looked_and_found_nothing_is_not_a_skip() -> None:
    outcome = AlwaysQuiet().run(quiet_context())
    assert not outcome.skipped
    assert outcome.looked_and_found_nothing
    assert str(outcome) == "TST-2 found nothing"


def test_evidence_under_the_wrong_code_is_caught() -> None:
    with pytest.raises(ConflictError, match="labelled OTHER"):
        Mislabelled().run(quiet_context())


def test_a_set_keeps_its_order_and_its_codes() -> None:
    rules = RuleSet([NeedsSound(), AlwaysQuiet()])
    assert rules.codes == ["TST-1", "TST-2"]
    assert len(rules) == 2
    assert "TST-1" in rules
    assert "TST-9" not in rules


def test_a_duplicate_code_is_refused() -> None:
    rules = RuleSet([NeedsSound()])
    with pytest.raises(ConflictError, match="in this set twice"):
        rules.add(NeedsSound())


def test_getting_a_rule_by_code() -> None:
    rules = RuleSet([NeedsSound(), AlwaysQuiet()])
    assert rules.get("TST-2").description.startswith("applies to everything")
    with pytest.raises(NotFoundError, match="rule"):
        rules.get("TST-9")


def test_dropping_a_rule_a_site_disagrees_with() -> None:
    rules = RuleSet([NeedsSound(), AlwaysQuiet()])
    trimmed = rules.without("TST-1")
    assert trimmed.codes == ["TST-2"]
    assert rules.codes == ["TST-1", "TST-2"]


def test_dropping_a_rule_that_is_not_there() -> None:
    with pytest.raises(NotFoundError, match="rule"):
        RuleSet([NeedsSound()]).without("TST-9")


def test_running_a_set_collects_the_evidence() -> None:
    findings = RuleSet([NeedsSound(), AlwaysQuiet()]).run(loud_context())
    assert len(findings) == 1
    assert findings.rules_fired == ["TST-1"]


def test_running_a_set_on_a_context_with_nothing_measured() -> None:
    findings = RuleSet([NeedsSound(), AlwaysQuiet()]).run(quiet_context())
    assert len(findings) == 0


def test_a_trace_keeps_the_skips() -> None:
    trace = RuleSet([NeedsSound(), AlwaysQuiet()]).trace(quiet_context())
    assert [o.skipped for o in trace] == [True, False]


def test_which_rules_apply() -> None:
    rules = RuleSet([NeedsSound(), AlwaysQuiet()])
    assert [r.code for r in rules.applicable_to(quiet_context())] == ["TST-2"]
    assert [r.code for r in rules.applicable_to(loud_context())] == ["TST-1", "TST-2"]


def test_printing_a_rule_and_a_set() -> None:
    assert str(NeedsSound()) == "TST-1 fires when there is an ultrasonic reading"
    assert str(RuleSet([NeedsSound()])) == "1 rules"


def test_an_empty_set_runs_and_finds_nothing() -> None:
    assert len(RuleSet().run(quiet_context())) == 0
    assert RuleSet().trace(quiet_context()) == []
