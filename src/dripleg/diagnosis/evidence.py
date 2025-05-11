"""One reason to believe something about a trap, and a bag of them.

The engine does not produce a condition. It produces evidence, and the verdict
falls out of the evidence afterwards. That ordering is deliberate and it is the
whole reason this module exists separately.

A steam trap survey report gets challenged. Not often, but when a plant is told
to spend forty thousand pounds on trap replacements, somebody senior reads the
line for the most expensive trap on the list and asks why. A verdict with no
reasons behind it cannot answer that, and a verdict assembled by a chain of if
statements can only answer it by having somebody read the code.

So each rule contributes one `Evidence`: which rule, what it saw, what that
points at, and how strongly. The verdict is a function of the set, and the set
is printed under the verdict in the report.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SurveyMethod

__all__ = ["Evidence", "EvidenceSet"]

MAX_WEIGHT = 1.0


@dataclass(frozen=True)
class Evidence:
    """One rule firing, and what it thinks that means."""

    rule: str
    statement: str
    supports: TrapCondition
    weight: float
    method: SurveyMethod

    def __post_init__(self) -> None:
        code = self.rule.strip().upper()
        if not code:
            raise ValidationError("evidence has to name the rule that made it", field="rule")
        object.__setattr__(self, "rule", code)
        said = " ".join(self.statement.split())
        if not said:
            raise ValidationError("evidence has to say what it saw", field="statement")
        object.__setattr__(self, "statement", said)
        if not 0.0 < self.weight <= MAX_WEIGHT:
            raise ValidationError(
                f"evidence weight sits in (0, {MAX_WEIGHT}], got {self.weight:g}",
                field="weight",
            )

    @property
    def is_decisive(self) -> bool:
        """Weight at the top of the scale: one rule that settles it on its own."""

        return self.weight >= MAX_WEIGHT

    def __str__(self) -> str:
        return f"{self.rule}: {self.statement} -> {self.supports.label} ({self.weight:.2f})"


class EvidenceSet:
    """Everything the rules had to say about one trap on one visit."""

    def __init__(self, evidence: Iterable[Evidence] = ()) -> None:
        self._evidence: list[Evidence] = list(evidence)

    def add(self, evidence: Evidence) -> None:
        self._evidence.append(evidence)

    def extend(self, evidence: Iterable[Evidence]) -> None:
        self._evidence.extend(evidence)

    def __len__(self) -> int:
        return len(self._evidence)

    def __iter__(self) -> Iterator[Evidence]:
        return iter(self._evidence)

    def __bool__(self) -> bool:
        return bool(self._evidence)

    @property
    def rules_fired(self) -> list[str]:
        return sorted({e.rule for e in self._evidence})

    @property
    def methods(self) -> set[SurveyMethod]:
        return {e.method for e in self._evidence}

    def supporting(self, condition: TrapCondition) -> list[Evidence]:
        return [e for e in self._evidence if e.supports is condition]

    def weight_for(self, condition: TrapCondition) -> float:
        """Total weight behind one condition, capped at one.

        Capped because three weak reasons to think a trap is leaking should not
        outrank one decisive reason to think it is blowing through, and without
        a cap they do.
        """

        return min(sum(e.weight for e in self.supporting(condition)), MAX_WEIGHT)

    def conditions(self) -> list[TrapCondition]:
        """Everything anything pointed at, strongest first."""

        seen = {e.supports for e in self._evidence}
        return sorted(seen, key=lambda c: (-self.weight_for(c), c.rank))

    def decisive_for(self, condition: TrapCondition) -> list[Evidence]:
        return [e for e in self.supporting(condition) if e.is_decisive]

    @property
    def is_contested(self) -> bool:
        """Whether two different conditions both have real support."""

        weights = sorted((self.weight_for(c) for c in self.conditions()), reverse=True)
        return len(weights) > 1 and weights[1] >= 0.4

    def strongest(self) -> Evidence | None:
        if not self._evidence:
            return None
        return max(self._evidence, key=lambda e: (e.weight, -e.supports.rank))

    def by_method(self, method: SurveyMethod) -> list[Evidence]:
        return [e for e in self._evidence if e.method is method]

    def lines(self) -> list[str]:
        """The reasons, in the order they should be printed under a verdict."""

        ordered = sorted(self._evidence, key=lambda e: (-e.weight, e.rule))
        return [str(e) for e in ordered]

    def __str__(self) -> str:
        if not self._evidence:
            return "no evidence"
        return f"{len(self._evidence)} findings from {len(self.methods)} methods"
