"""What to order off the back of a work list.

A ranked list of forty jobs is not a purchase order. The storeroom wants one
line per part with a quantity on it, and it wants the quantity to be right,
because a crew that arrives at the third trap of the day without the kit for it
loses the day.

Two lines come off each job. A repair needs a kit for the model that is fitted.
A replacement needs the trap that is going in, which is not always the model
that is coming out. Cleaning a strainer needs nothing at all, and a job that
needs nothing still belongs on the list so the planner can see the whole day.

Quantities carry a spare allowance, because the seventh trap of a batch is
always the one with the seized union. The allowance rounds down, so a list of
one job orders one part: rounding a single job up to two is how a storeroom
ends up with forty spare kits it will never fit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.repair.priority import RankedJob, WorkList
from dripleg.repair.recommend import Action
from dripleg.units.money import Money

__all__ = ["SparesLine", "SparesList", "build_spares_list"]

DEFAULT_ALLOWANCE = 0.10


@dataclass(frozen=True)
class SparesLine:
    """One part, and how many of it the work list needs."""

    manufacturer: str
    code: str
    part: str
    jobs: int
    quantity: int
    unit_price: Money

    def __post_init__(self) -> None:
        if self.jobs < 1:
            raise ValidationError("a spares line covers at least one job", field="jobs")
        if self.quantity < self.jobs:
            raise ValidationError(
                "a spares line cannot order fewer parts than jobs", field="quantity"
            )

    @property
    def total(self) -> Money:
        return self.unit_price.scaled(self.quantity)

    @property
    def spare(self) -> int:
        return self.quantity - self.jobs

    def __str__(self) -> str:
        return (
            f"{self.quantity} x {self.manufacturer} {self.code} {self.part} "
            f"for {self.jobs} jobs, {self.total}"
        )


@dataclass(frozen=True)
class SparesList:
    """Every part one work list needs, dearest line first."""

    lines: list[SparesLine]
    jobs_needing_nothing: int
    allowance: float

    @property
    def total(self) -> Money:
        total = Money.zero()
        for line in self.lines:
            total = total + line.total
        return total

    @property
    def parts(self) -> int:
        return sum(line.quantity for line in self.lines)

    def of_part(self, part: str) -> list[SparesLine]:
        return [line for line in self.lines if line.part == part]

    def __str__(self) -> str:
        return (
            f"{len(self.lines)} lines, {self.parts} parts, {self.total}, "
            f"{self.jobs_needing_nothing} jobs needing nothing"
        )


def _kit_price(job: RankedJob) -> Money:
    """A repair kit is the parts cost the recommendation already worked out."""

    return job.job.parts


def build_spares_list(work: WorkList, allowance: float = DEFAULT_ALLOWANCE) -> SparesList:
    """Roll a work list up into one line per part."""

    if not 0.0 <= allowance < 1.0:
        raise ValidationError("a spares allowance sits in [0, 1)", field="allowance")
    counts: dict[tuple[str, str, str], list[Money]] = {}
    nothing = 0
    for ranked in work.actionable:
        action = ranked.job.action
        if action is Action.CLEAN:
            nothing += 1
            continue
        if action is Action.REPAIR:
            model = ranked.row.station.model
            key = (model.manufacturer, model.code, "repair kit")
            price = _kit_price(ranked)
        else:
            replacement = ranked.job.replacement
            if replacement is None:
                nothing += 1
                continue
            key = (replacement.manufacturer, replacement.code, "trap")
            price = replacement.list_price
        counts.setdefault(key, []).append(price)
    lines: list[SparesLine] = []
    for (manufacturer, code, part), prices in counts.items():
        jobs = len(prices)
        quantity = jobs + math.floor(jobs * allowance)
        cheapest = min(prices, key=lambda money: money.cents)
        lines.append(
            SparesLine(
                manufacturer=manufacturer,
                code=code,
                part=part,
                jobs=jobs,
                quantity=quantity,
                unit_price=cheapest,
            )
        )
    return SparesList(
        lines=sorted(lines, key=lambda line: (-line.total.cents, line.code)),
        jobs_needing_nothing=nothing,
        allowance=allowance,
    )
