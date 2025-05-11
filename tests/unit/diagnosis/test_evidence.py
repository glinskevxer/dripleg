from __future__ import annotations

import pytest

from dripleg.diagnosis.evidence import Evidence, EvidenceSet
from dripleg.errors import ValidationError
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SurveyMethod


def sound(
    rule: str = "SND-1",
    condition: TrapCondition = TrapCondition.BLOWING_THROUGH,
    weight: float = 0.6,
) -> Evidence:
    return Evidence(
        rule=rule,
        statement="68 dB with no cycling on a disc trap",
        supports=condition,
        weight=weight,
        method=SurveyMethod.ULTRASONIC,
    )


def heat(
    rule: str = "TMP-1",
    condition: TrapCondition = TrapCondition.BLOWING_THROUGH,
    weight: float = 0.5,
) -> Evidence:
    return Evidence(
        rule=rule,
        statement="7 F across the trap",
        supports=condition,
        weight=weight,
        method=SurveyMethod.CONTACT_TEMPERATURE,
    )


def test_evidence_normalises_its_rule_and_statement() -> None:
    item = Evidence(
        rule=" snd-1 ",
        statement="  68 dB   steady ",
        supports=TrapCondition.LEAKING,
        weight=0.5,
        method=SurveyMethod.ULTRASONIC,
    )
    assert item.rule == "SND-1"
    assert item.statement == "68 dB steady"


def test_evidence_needs_a_rule_and_a_statement() -> None:
    with pytest.raises(ValidationError, match="name the rule"):
        sound(rule="   ")
    with pytest.raises(ValidationError, match="say what it saw"):
        Evidence(
            rule="SND-1",
            statement="  ",
            supports=TrapCondition.OK,
            weight=0.5,
            method=SurveyMethod.ULTRASONIC,
        )


def test_a_weight_has_to_be_in_range() -> None:
    for bad in (0.0, -0.2, 1.5):
        with pytest.raises(ValidationError, match="weight sits in"):
            sound(weight=bad)


def test_full_weight_is_decisive() -> None:
    assert sound(weight=1.0).is_decisive
    assert not sound(weight=0.99).is_decisive


def test_an_empty_set_says_so() -> None:
    empty = EvidenceSet()
    assert not empty
    assert len(empty) == 0
    assert empty.strongest() is None
    assert empty.conditions() == []
    assert str(empty) == "no evidence"
    assert empty.lines() == []


def test_a_set_collects_and_reports_its_rules() -> None:
    findings = EvidenceSet([sound(), heat()])
    findings.add(sound("SND-2", weight=0.3))
    assert len(findings) == 3
    assert findings.rules_fired == ["SND-1", "SND-2", "TMP-1"]
    assert findings.methods == {SurveyMethod.ULTRASONIC, SurveyMethod.CONTACT_TEMPERATURE}


def test_extending_a_set() -> None:
    findings = EvidenceSet()
    findings.extend([sound(), heat()])
    assert len(findings) == 2


def test_weight_adds_up_per_condition_and_is_capped() -> None:
    findings = EvidenceSet([sound(weight=0.6), heat(weight=0.5), sound("SND-2", weight=0.4)])
    assert findings.weight_for(TrapCondition.BLOWING_THROUGH) == pytest.approx(1.0)
    assert findings.weight_for(TrapCondition.OK) == 0.0


def test_supporting_pulls_out_one_conditions_reasons() -> None:
    findings = EvidenceSet([sound(), heat(condition=TrapCondition.OK, weight=0.2)])
    assert len(findings.supporting(TrapCondition.BLOWING_THROUGH)) == 1
    assert len(findings.supporting(TrapCondition.OK)) == 1
    assert findings.supporting(TrapCondition.PLUGGED) == []


def test_conditions_come_back_strongest_first() -> None:
    findings = EvidenceSet(
        [
            sound(condition=TrapCondition.LEAKING, weight=0.3),
            heat(condition=TrapCondition.BLOWING_THROUGH, weight=0.8),
        ]
    )
    assert findings.conditions() == [TrapCondition.BLOWING_THROUGH, TrapCondition.LEAKING]


def test_a_tie_on_weight_falls_back_to_the_worse_condition() -> None:
    findings = EvidenceSet(
        [
            sound(condition=TrapCondition.LEAKING, weight=0.5),
            heat(condition=TrapCondition.BLOWING_THROUGH, weight=0.5),
        ]
    )
    assert findings.conditions()[0] is TrapCondition.BLOWING_THROUGH


def test_decisive_evidence_can_be_picked_out() -> None:
    findings = EvidenceSet([sound(weight=1.0), heat(weight=0.4)])
    decisive = findings.decisive_for(TrapCondition.BLOWING_THROUGH)
    assert len(decisive) == 1
    assert decisive[0].rule == "SND-1"


def test_a_set_is_contested_when_two_conditions_both_have_support() -> None:
    contested = EvidenceSet(
        [
            sound(condition=TrapCondition.BLOWING_THROUGH, weight=0.6),
            heat(condition=TrapCondition.FAILED_CLOSED, weight=0.5),
        ]
    )
    assert contested.is_contested


def test_a_weak_second_opinion_does_not_make_it_contested() -> None:
    findings = EvidenceSet(
        [
            sound(condition=TrapCondition.BLOWING_THROUGH, weight=0.9),
            heat(condition=TrapCondition.LEAKING, weight=0.2),
        ]
    )
    assert not findings.is_contested


def test_one_condition_alone_is_never_contested() -> None:
    assert not EvidenceSet([sound()]).is_contested
    assert not EvidenceSet().is_contested


def test_the_strongest_finding() -> None:
    findings = EvidenceSet([sound(weight=0.4), heat(weight=0.9)])
    strongest = findings.strongest()
    assert strongest is not None
    assert strongest.rule == "TMP-1"


def test_findings_can_be_split_by_method() -> None:
    findings = EvidenceSet([sound(), heat()])
    assert len(findings.by_method(SurveyMethod.ULTRASONIC)) == 1
    assert findings.by_method(SurveyMethod.SIGHT_GLASS) == []


def test_the_printed_reasons_lead_with_the_strongest() -> None:
    findings = EvidenceSet([sound(weight=0.4), heat(weight=0.9)])
    lines = findings.lines()
    assert lines[0].startswith("TMP-1:")
    assert "blowing through" in lines[0]
    assert str(findings) == "2 findings from 2 methods"
