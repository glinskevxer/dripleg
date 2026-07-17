"""Which rules are doing any work, and which are only ever skipped.

A rule set grows and never shrinks, and after a few years a fair share of it
is dead: rules whose readings nobody takes any more, rules whose thresholds are
wrong for this plant so they never fire, and rules that fire on everything and
therefore separate nothing.

Three counts tell those apart. Skipped means the reading it needs was not
taken. Silent means it looked and found nothing. Fired means it produced
evidence. A rule that is always skipped is a survey method problem. A rule that
is never silent is a threshold problem.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.rules import RuleSet
from dripleg.errors import ValidationError

__all__ = ["RuleCoverage", "RuleUse", "measure_coverage"]


@dataclass(frozen=True)
class RuleUse:
    """What one rule did across a set of readings."""

    code: str
    description: str
    skipped: int
    silent: int
    fired: int

    def __post_init__(self) -> None:
        if min(self.skipped, self.silent, self.fired) < 0:
            raise ValidationError("a rule count is not negative", field="skipped")

    @property
    def seen(self) -> int:
        return self.skipped + self.silent + self.fired

    @property
    def applied(self) -> int:
        return self.silent + self.fired

    @property
    def fire_rate(self) -> float:
        if self.applied == 0:
            return 0.0
        return self.fired / self.applied

    @property
    def is_dead(self) -> bool:
        """Never fired on anything it looked at."""

        return self.seen > 0 and self.fired == 0

    @property
    def is_never_applied(self) -> bool:
        """The reading it needs is never taken."""

        return self.seen > 0 and self.applied == 0

    @property
    def separates_nothing(self) -> bool:
        """Fires on everything it looks at, so it tells one trap from no other."""

        return self.applied >= 5 and self.fired == self.applied

    def __str__(self) -> str:
        if self.is_never_applied:
            return f"{self.code}: never applied, the reading is not taken"
        return (
            f"{self.code}: fired on {self.fired} of {self.applied} "
            f"({self.fire_rate:.0%}), skipped {self.skipped}"
        )


@dataclass(frozen=True)
class RuleCoverage:
    """The whole rule set across one survey."""

    readings: int
    uses: list[RuleUse]

    def find(self, code: str) -> RuleUse | None:
        for use in self.uses:
            if use.code == code.strip().upper():
                return use
        return None

    @property
    def dead(self) -> list[RuleUse]:
        return [use for use in self.uses if use.is_dead]

    @property
    def never_applied(self) -> list[RuleUse]:
        return [use for use in self.uses if use.is_never_applied]

    @property
    def indiscriminate(self) -> list[RuleUse]:
        return [use for use in self.uses if use.separates_nothing]

    @property
    def working(self) -> list[RuleUse]:
        return [use for use in self.uses if use.fired and not use.separates_nothing]

    def __str__(self) -> str:
        return (
            f"{len(self.uses)} rules over {self.readings} readings: "
            f"{len(self.working)} working, {len(self.dead)} dead"
        )


def measure_coverage(rules: RuleSet, contexts: list[DiagnosisContext]) -> RuleCoverage:
    """Run the set over a batch of readings, counting what each rule did."""

    counts: dict[str, list[int]] = {rule.code: [0, 0, 0] for rule in rules}
    descriptions = {rule.code: rule.description for rule in rules}
    for context in contexts:
        for outcome in rules.trace(context):
            row = counts[outcome.rule.code]
            if outcome.skipped:
                row[0] += 1
            elif outcome.fired:
                row[2] += 1
            else:
                row[1] += 1
    return RuleCoverage(
        readings=len(contexts),
        uses=[
            RuleUse(
                code=code,
                description=descriptions[code],
                skipped=skipped,
                silent=silent,
                fired=fired,
            )
            for code, (skipped, silent, fired) in counts.items()
        ],
    )
