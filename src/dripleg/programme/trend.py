"""Comparing two surveys, which is the only way to tell a programme is working.

A single survey says how much is being lost. Two surveys say whether anybody
did anything about it, and they say it in four buckets that have to be kept
apart:

- fixed: failed last time, passing now, which is the programme working
- still failing: failed both times, which is the programme not working, and is
  the most expensive bucket because the loss has run for another whole cycle
- newly failed: passing last time, failing now, which is the population's
  natural failure rate and is what the interval is supposed to catch
- unchanged: passing both times

A headline that says the failure rate fell from eighteen to twelve percent
hides all four. A plant can halve its failure rate while the same six traps
blow all year, and the trap that has been on the list three surveys running is
the one somebody needs to walk to.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.tags import TrapTag
from dripleg.store.finding_repo import StoredFinding
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money

__all__ = ["Movement", "Trend", "compare_surveys"]


@dataclass(frozen=True)
class Movement:
    """One trap, and what it did between the two surveys."""

    tag: TrapTag
    before: TrapCondition
    after: TrapCondition
    cost_before: Money
    cost_after: Money

    @property
    def was_failing(self) -> bool:
        return self.before.is_failure

    @property
    def is_failing(self) -> bool:
        return self.after.is_failure

    @property
    def bucket(self) -> str:
        if self.was_failing and not self.is_failing:
            return "fixed"
        if self.was_failing and self.is_failing:
            return "still failing"
        if not self.was_failing and self.is_failing:
            return "newly failed"
        return "unchanged"

    @property
    def saving(self) -> Money:
        return self.cost_before - self.cost_after

    def __str__(self) -> str:
        return f"{self.tag} {self.before.label} to {self.after.label} ({self.bucket})"


@dataclass(frozen=True)
class Trend:
    """Two surveys held against each other."""

    earlier: str
    later: str
    movements: list[Movement]
    only_earlier: list[TrapTag]
    only_later: list[TrapTag]

    def in_bucket(self, bucket: str) -> list[Movement]:
        known = {"fixed", "still failing", "newly failed", "unchanged"}
        if bucket not in known:
            raise ValidationError(
                f"{bucket!r} is not a bucket, expected one of: {', '.join(sorted(known))}",
                field="bucket",
            )
        return [m for m in self.movements if m.bucket == bucket]

    @property
    def compared(self) -> int:
        return len(self.movements)

    @property
    def failing_before(self) -> int:
        return len([m for m in self.movements if m.was_failing])

    @property
    def failing_after(self) -> int:
        return len([m for m in self.movements if m.is_failing])

    @property
    def failure_rate_before(self) -> float:
        if not self.movements:
            return 0.0
        return self.failing_before / self.compared

    @property
    def failure_rate_after(self) -> float:
        if not self.movements:
            return 0.0
        return self.failing_after / self.compared

    @property
    def cost_before(self) -> Money:
        total = Money.zero()
        for movement in self.movements:
            total = total + movement.cost_before
        return total

    @property
    def cost_after(self) -> Money:
        total = Money.zero()
        for movement in self.movements:
            total = total + movement.cost_after
        return total

    @property
    def saving(self) -> Money:
        return self.cost_before - self.cost_after

    @property
    def unfixed_cost(self) -> Money:
        """What the traps that failed twice running are still costing."""

        total = Money.zero()
        for movement in self.in_bucket("still failing"):
            total = total + movement.cost_after
        return total

    @property
    def is_improving(self) -> bool:
        return self.failure_rate_after < self.failure_rate_before

    def counts(self) -> dict[str, int]:
        return {
            bucket: len(self.in_bucket(bucket))
            for bucket in ("fixed", "still failing", "newly failed", "unchanged")
        }

    def __str__(self) -> str:
        counts = self.counts()
        return (
            f"{self.earlier} to {self.later}: {counts['fixed']} fixed, "
            f"{counts['still failing']} still failing, {counts['newly failed']} newly failed"
        )


def compare_surveys(earlier: list[StoredFinding], later: list[StoredFinding]) -> Trend:
    """Line two saved survey registers up trap by trap."""

    if not earlier and not later:
        raise ValidationError("there is nothing to compare", field="findings")
    before = {f.tag: f for f in earlier}
    after = {f.tag: f for f in later}
    shared = sorted(set(before) & set(after))
    return Trend(
        earlier=earlier[0].survey_reference if earlier else "",
        later=later[0].survey_reference if later else "",
        movements=[
            Movement(
                tag=tag,
                before=before[tag].diagnosed,
                after=after[tag].diagnosed,
                cost_before=before[tag].annual_cost,
                cost_after=after[tag].annual_cost,
            )
            for tag in shared
        ],
        only_earlier=sorted(set(before) - set(after)),
        only_later=sorted(set(after) - set(before)),
    )
