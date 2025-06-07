"""Turning a bag of evidence into one verdict, with the reasons kept.

The precedence here is short and it is the only place in the package that
decides anything about a trap. Four steps, in this order:

1. A trap that was never reached keeps the code the technician wrote. There is
   nothing to diagnose and pretending otherwise invents a finding.
2. Decisive evidence wins outright. Only a sight glass produces it.
3. A dead line beats everything else. A trap on an isolated header cannot be
   blowing steam through, whatever the seat sounds like, so a strong out of
   service finding cuts the rest off rather than competing with it.
4. Otherwise the heaviest condition wins, and a tie goes to the worse one.

Confidence is the weight behind the winner, knocked down when the evidence is
contested or when it all came from one method. That reduction is the whole
reason a single method survey is worth less: not because the readings are
wrong, but because nothing corroborates them. Decisive evidence is exempt, for
the same reason: a sight glass showing live steam does not need the probe to
agree with it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from dripleg.diagnosis.combined_rules import COMBINED_RULES
from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.evidence import EvidenceSet
from dripleg.diagnosis.heat_rules import HEAT_RULES
from dripleg.diagnosis.rules import RuleSet
from dripleg.diagnosis.sound_rules import SOUND_RULES
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition

__all__ = ["DEFAULT_RULES", "Diagnosis", "DiagnosisEngine"]

DEFAULT_RULES = RuleSet([*SOUND_RULES, *HEAT_RULES, *COMBINED_RULES])

_CONTESTED_PENALTY = 0.25
_SINGLE_METHOD_PENALTY = 0.20
_OUT_OF_SERVICE_FLOOR = 0.6


@dataclass(frozen=True)
class Diagnosis:
    """What the rules made of one trap on one visit."""

    tag: TrapTag
    observed_on: dt.date
    condition: TrapCondition
    confidence: float
    evidence: EvidenceSet
    reported_condition: TrapCondition
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def agrees_with_technician(self) -> bool:
        return self.condition is self.reported_condition

    @property
    def is_provisional(self) -> bool:
        """Whether this verdict should be flagged rather than acted on."""

        return self.confidence < 0.5 or "single method" in self.flags

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence)

    @property
    def severity_factor(self) -> float:
        return self.condition.severity_factor

    def reasons(self) -> list[str]:
        return self.evidence.lines()

    def __str__(self) -> str:
        return (
            f"{self.tag} {self.observed_on} {self.condition.label} "
            f"({self.confidence:.0%} confident)"
        )


class DiagnosisEngine:
    """Runs a rule set and applies the precedence."""

    def __init__(self, rules: RuleSet | None = None) -> None:
        self.rules = rules if rules is not None else DEFAULT_RULES

    def diagnose(self, context: DiagnosisContext) -> Diagnosis:
        reported = context.observation.reported_condition
        flags = self._flags(context)
        if not reported.was_assessed:
            return Diagnosis(
                tag=context.station.tag,
                observed_on=context.observed_on,
                condition=reported,
                confidence=1.0,
                evidence=EvidenceSet(),
                reported_condition=reported,
                flags=(*flags, "not assessed"),
            )
        findings = self.rules.run(context)
        condition, confidence = self._decide(findings, reported)
        # Decisive evidence is not knocked down for standing alone. A sight
        # glass showing live steam is the corroboration, and asking the probe
        # to agree with it before believing it has the two backwards.
        decisive = bool(findings.decisive_for(condition))
        if findings.is_contested:
            flags = (*flags, "contested")
            if not decisive:
                confidence = max(confidence - _CONTESTED_PENALTY, 0.0)
        if len(findings.methods) < 2 and findings:
            flags = (*flags, "single method")
            if not decisive:
                confidence = max(confidence - _SINGLE_METHOD_PENALTY, 0.0)
        if condition is not reported:
            flags = (*flags, "differs from the field code")
        return Diagnosis(
            tag=context.station.tag,
            observed_on=context.observed_on,
            condition=condition,
            confidence=round(confidence, 3),
            evidence=findings,
            reported_condition=reported,
            flags=flags,
        )

    @staticmethod
    def _decide(findings: EvidenceSet, reported: TrapCondition) -> tuple[TrapCondition, float]:
        if not findings:
            return reported, 0.0
        for condition in findings.conditions():
            if findings.decisive_for(condition):
                return condition, 1.0
        out_of_service = findings.weight_for(TrapCondition.OUT_OF_SERVICE)
        if out_of_service >= _OUT_OF_SERVICE_FLOOR:
            return TrapCondition.OUT_OF_SERVICE, out_of_service
        winner = findings.conditions()[0]
        return winner, findings.weight_for(winner)

    @staticmethod
    def _flags(context: DiagnosisContext) -> tuple[str, ...]:
        flags: list[str] = []
        if context.pressure_disagrees_with_register:
            flags.append("measured pressure is a long way off the register")
        if not context.observation.is_two_method and context.observation.has_measurements:
            flags.append("one method only")
        if not context.observation.has_measurements:
            flags.append("no readings taken")
        return tuple(flags)

    def diagnose_all(self, contexts: list[DiagnosisContext]) -> list[Diagnosis]:
        return [self.diagnose(context) for context in contexts]
