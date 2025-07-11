"""Ranking the jobs, and cutting the list where the budget runs out.

Money alone is the wrong order to send a crew out in, and it is the order every
spreadsheet produces. The dearest leak on the site can be a tracer on a line
that comes down in six weeks anyway, and the cheapest can be the one holding
condensate into a turbine drain.

So the score is four things multiplied: what the loss is worth, what the trap
matters for, how sure the diagnosis is, and how quickly the job pays for
itself. A safety trap with a modest loss and a certain diagnosis outranks a
large loss on a nuisance line that nobody is sure about, which is what a
planner would do by hand.

The budget cut is separate and deliberately dumb: walk the ranked list, take
jobs until the money runs out, and report what got left. Anything cleverer is a
knapsack solver producing an order nobody can explain to the crew.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from dripleg.errors import ValidationError
from dripleg.loss.register import TrapLoss
from dripleg.repair.recommend import Recommendation
from dripleg.units.money import Money

__all__ = ["Priority", "RankedJob", "WorkList", "rank_jobs", "score_job"]

_SAFETY_FLOOR = 4.0


class Priority(Enum):
    IMMEDIATE = "immediate"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    DEFERRED = "deferred"

    @property
    def label(self) -> str:
        return self.value

    @property
    def within_days(self) -> int:
        return {
            Priority.IMMEDIATE: 7,
            Priority.HIGH: 30,
            Priority.MEDIUM: 90,
            Priority.LOW: 180,
            Priority.DEFERRED: 365,
        }[self]

    @classmethod
    def from_score(cls, score: float) -> Priority:
        if score >= _SAFETY_FLOOR:
            return cls.IMMEDIATE
        if score >= 2.0:
            return cls.HIGH
        if score >= 1.0:
            return cls.MEDIUM
        if score > 0.0:
            return cls.LOW
        return cls.DEFERRED


def score_job(row: TrapLoss, job: Recommendation) -> float:
    """A number nobody should read, used only to sort.

    Loss is logged rather than linear, because otherwise one enormous leak
    holds the top four places and the crew never gets past it.
    """

    if not job.action.is_work:
        return 0.0
    # A safety trap holding condensate back is the most urgent job on the site
    # and it wastes no steam at all, so this has to come before the money.
    if row.station.criticality.escalates_immediately and row.condition.blocks_condensate:
        return _SAFETY_FLOOR
    dollars = job.annual_saving.cents / 100.0
    if dollars <= 0:
        return 0.0
    loss_term = math.log10(1.0 + dollars) / 3.0
    criticality = row.station.criticality.weight
    confidence = max(row.diagnosis.confidence, 0.2)
    payback = job.payback_years
    payback_term = 1.0 if payback is None else 1.0 / (1.0 + payback)
    score = loss_term * criticality * confidence * (0.5 + payback_term)
    return round(score, 4)


@dataclass(frozen=True)
class RankedJob:
    """One job with its score and the band that falls out of it."""

    row: TrapLoss
    job: Recommendation
    score: float

    @property
    def priority(self) -> Priority:
        return Priority.from_score(self.score)

    @property
    def cost(self) -> Money:
        return self.job.cost

    @property
    def saving(self) -> Money:
        return self.job.annual_saving

    def __str__(self) -> str:
        return f"{self.priority.label:<9} {self.job}"


def rank_jobs(pairs: list[tuple[TrapLoss, Recommendation]]) -> list[RankedJob]:
    """Score everything and sort it, worst first, tag order inside a tie."""

    ranked = [RankedJob(row=row, job=job, score=score_job(row, job)) for row, job in pairs]
    return sorted(ranked, key=lambda r: (-r.score, str(r.row.tag)))


class WorkList:
    """A ranked list of jobs, and what fits inside a budget."""

    def __init__(self, jobs: list[RankedJob]) -> None:
        self.jobs = jobs

    def __len__(self) -> int:
        return len(self.jobs)

    @property
    def actionable(self) -> list[RankedJob]:
        return [ranked for ranked in self.jobs if ranked.job.action.is_work]

    @property
    def total_cost(self) -> Money:
        total = Money.zero()
        for ranked in self.actionable:
            total = total + ranked.cost
        return total

    @property
    def total_saving(self) -> Money:
        total = Money.zero()
        for ranked in self.actionable:
            total = total + ranked.saving
        return total

    def in_band(self, priority: Priority) -> list[RankedJob]:
        return [ranked for ranked in self.jobs if ranked.priority is priority]

    def within(self, budget: Money) -> tuple[list[RankedJob], list[RankedJob]]:
        """Walk the ranked list until the money runs out.

        A job that does not fit is skipped and the walk carries on, because a
        crew that stops at the first job it cannot afford leaves cheap work
        undone for no reason.
        """

        if budget.cents < 0:
            raise ValidationError("a budget is not negative", field="budget")
        remaining = budget
        taken: list[RankedJob] = []
        left: list[RankedJob] = []
        for ranked in self.actionable:
            if ranked.cost.cents <= remaining.cents:
                taken.append(ranked)
                remaining = remaining - ranked.cost
            else:
                left.append(ranked)
        return taken, left

    def payback_on(self, jobs: list[RankedJob]) -> float | None:
        cost = Money.zero()
        saving = Money.zero()
        for ranked in jobs:
            cost = cost + ranked.cost
            saving = saving + ranked.saving
        return cost.payback_years(saving)

    def __str__(self) -> str:
        return (
            f"{len(self.actionable)} jobs, {self.total_cost} to do, {self.total_saving} a year back"
        )
