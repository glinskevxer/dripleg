"""The shape of a rule, and the set that runs them.

A rule is small on purpose. It answers one question about one context and
either says nothing or produces evidence. It never looks at what another rule
decided, and it never short circuits the ones after it. Rules that talk to each
other are how a rule set becomes unreadable by the second revision, and the
whole reason the verdict is computed from evidence afterwards is so that they
do not have to.

Two properties are enforced here rather than left to discipline:

- a rule that does not apply produces nothing, and applying is a separate
  question from what it found, so the coverage report can say a rule was
  skipped rather than that it passed
- rule codes are unique inside a set, because the report prints the code and a
  duplicate makes a finding untraceable
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.evidence import Evidence, EvidenceSet
from dripleg.errors import ConflictError, NotFoundError, ValidationError
from dripleg.survey.readings import SurveyMethod

__all__ = ["Rule", "RuleOutcome", "RuleSet"]


class Rule(ABC):
    """One question about one trap on one visit."""

    code: str = ""
    description: str = ""
    method: SurveyMethod = SurveyMethod.VISUAL

    def __init__(self) -> None:
        if not self.code.strip():
            raise ValidationError(f"{type(self).__name__} has no rule code", field="code")
        if not self.description.strip():
            raise ValidationError(f"rule {self.code} has no description", field="description")

    @abstractmethod
    def applies_to(self, context: DiagnosisContext) -> bool:
        """Whether this rule has the readings it needs."""

    @abstractmethod
    def look(self, context: DiagnosisContext) -> list[Evidence]:
        """What this rule found. Called only when it applies."""

    def run(self, context: DiagnosisContext) -> RuleOutcome:
        if not self.applies_to(context):
            return RuleOutcome(rule=self, skipped=True, evidence=[])
        found = self.look(context)
        for item in found:
            if item.rule != self.code:
                raise ConflictError(f"rule {self.code} produced evidence labelled {item.rule}")
        return RuleOutcome(rule=self, skipped=False, evidence=found)

    def __str__(self) -> str:
        return f"{self.code} {self.description}"


class RuleOutcome:
    """What one rule did on one context, including doing nothing."""

    def __init__(self, rule: Rule, skipped: bool, evidence: list[Evidence]) -> None:
        self.rule = rule
        self.skipped = skipped
        self.evidence = evidence

    @property
    def fired(self) -> bool:
        return bool(self.evidence)

    @property
    def looked_and_found_nothing(self) -> bool:
        return not self.skipped and not self.evidence

    def __str__(self) -> str:
        if self.skipped:
            return f"{self.rule.code} skipped"
        if not self.evidence:
            return f"{self.rule.code} found nothing"
        return f"{self.rule.code} produced {len(self.evidence)}"


class RuleSet:
    """An ordered set of rules with unique codes."""

    def __init__(self, rules: Iterable[Rule] = ()) -> None:
        self._rules: list[Rule] = []
        for rule in rules:
            self.add(rule)

    def add(self, rule: Rule) -> None:
        if any(existing.code == rule.code for existing in self._rules):
            raise ConflictError(f"rule {rule.code} is in this set twice")
        self._rules.append(rule)

    def __len__(self) -> int:
        return len(self._rules)

    def __iter__(self) -> Iterator[Rule]:
        return iter(self._rules)

    def __contains__(self, code: object) -> bool:
        return any(rule.code == code for rule in self._rules)

    @property
    def codes(self) -> list[str]:
        return [rule.code for rule in self._rules]

    def get(self, code: str) -> Rule:
        for rule in self._rules:
            if rule.code == code:
                return rule
        raise NotFoundError("rule", code)

    def without(self, *codes: str) -> RuleSet:
        """A copy with some rules taken out, for a site that disagrees with one."""

        dropped = set(codes)
        unknown = dropped - set(self.codes)
        if unknown:
            raise NotFoundError("rule", sorted(unknown)[0])
        return RuleSet(rule for rule in self._rules if rule.code not in dropped)

    def run(self, context: DiagnosisContext) -> EvidenceSet:
        findings = EvidenceSet()
        for outcome in self.trace(context):
            findings.extend(outcome.evidence)
        return findings

    def trace(self, context: DiagnosisContext) -> list[RuleOutcome]:
        """Run everything and keep the skips, which the coverage report wants."""

        return [rule.run(context) for rule in self._rules]

    def applicable_to(self, context: DiagnosisContext) -> list[Rule]:
        return [rule for rule in self._rules if rule.applies_to(context)]

    def __str__(self) -> str:
        return f"{len(self._rules)} rules"
