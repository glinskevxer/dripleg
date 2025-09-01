"""The work list, rendered, with the budget line drawn on it.

This is the page the maintenance planner keeps. Everything above the line is
this quarter's work and everything below it is the argument for next quarter's
budget, which is why the two are printed together rather than as two reports.

The cumulative saving column is the one that does the arguing. A planner
looking at forty jobs cannot hold the running total in their head, and the
point at which the cumulative saving stops climbing steeply is the point where
the programme stops being obviously worth it.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.repair.priority import Priority, RankedJob, WorkList
from dripleg.report.table import Column, Table
from dripleg.units.money import Money

__all__ = ["WorkReport", "build_work_report"]


@dataclass(frozen=True)
class JobLine:
    """One job as it appears on the list."""

    tag: str
    priority: str
    action: str
    reason: str
    cost: Money
    saving: Money
    payback: float | None
    cumulative_cost: Money
    cumulative_saving: Money
    inside_budget: bool

    @property
    def payback_text(self) -> str:
        if self.payback is None:
            return "never"
        if self.payback < 0.1:
            return "at once"
        return f"{self.payback:.1f} y"

    def as_dict(self) -> dict[str, object]:
        return {
            "tag": self.tag,
            "priority": self.priority,
            "action": self.action,
            "reason": self.reason,
            "cost_cents": self.cost.cents,
            "saving_cents": self.saving.cents,
            "payback_years": self.payback,
            "cumulative_cost_cents": self.cumulative_cost.cents,
            "cumulative_saving_cents": self.cumulative_saving.cents,
            "inside_budget": self.inside_budget,
        }


@dataclass(frozen=True)
class WorkReport:
    """A ranked work list, with or without a budget drawn across it."""

    site: str
    lines_in: list[JobLine]
    budget: Money | None
    total_cost: Money
    total_saving: Money

    @property
    def jobs(self) -> int:
        return len(self.lines_in)

    @property
    def inside(self) -> list[JobLine]:
        return [line for line in self.lines_in if line.inside_budget]

    @property
    def outside(self) -> list[JobLine]:
        return [line for line in self.lines_in if not line.inside_budget]

    @property
    def payback_years(self) -> float | None:
        return self.total_cost.payback_years(self.total_saving)

    @property
    def headline(self) -> str:
        if self.budget is None:
            return (
                f"{self.site}: {self.jobs} jobs, {self.total_cost} to do, "
                f"{self.total_saving} a year back"
            )
        return (
            f"{self.site}: {len(self.inside)} of {self.jobs} jobs inside {self.budget}, "
            f"{self.total_saving} a year back"
        )

    def table(self) -> Table:
        table = Table(
            [
                Column("tag"),
                Column("priority"),
                Column("action"),
                Column.number("cost"),
                Column.number("a year"),
                Column.number("payback"),
                Column.number("cum. saving"),
                Column("reason", max_width=40),
            ]
        )
        for line in self.lines_in:
            table.add(
                [
                    line.tag,
                    line.priority,
                    line.action,
                    str(line.cost),
                    str(line.saving),
                    line.payback_text,
                    str(line.cumulative_saving),
                    line.reason,
                ]
            )
        return table

    def band_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for line in self.lines_in:
            counts[line.priority] = counts.get(line.priority, 0) + 1
        return counts

    def lines(self) -> list[str]:
        out = [self.headline, ""]
        out.extend(self.table().lines())
        if self.budget is not None and self.outside:
            out.extend(
                [
                    "",
                    f"{len(self.outside)} jobs fall outside the budget and carry "
                    f"{self._outside_saving()} a year between them",
                ]
            )
        payback = self.payback_years
        if payback is not None:
            out.extend(["", f"the list as a whole pays back in {payback:.1f} years"])
        return out

    def _outside_saving(self) -> Money:
        total = Money.zero()
        for line in self.outside:
            total = total + line.saving
        return total

    def render(self) -> str:
        return "\n".join(self.lines())

    def as_dict(self) -> dict[str, object]:
        return {
            "site": self.site,
            "jobs": self.jobs,
            "budget_cents": None if self.budget is None else self.budget.cents,
            "total_cost_cents": self.total_cost.cents,
            "total_saving_cents": self.total_saving.cents,
            "payback_years": self.payback_years,
            "bands": self.band_counts(),
            "lines": [line.as_dict() for line in self.lines_in],
        }


def build_work_report(
    site: str,
    work: WorkList,
    budget: Money | None = None,
    band: Priority | None = None,
) -> WorkReport:
    """Lay a ranked list out, carrying the running totals down it."""

    ranked: list[RankedJob] = work.actionable
    if band is not None:
        ranked = [job for job in ranked if job.priority is band]
    taken: set[str] = set()
    if budget is not None:
        inside, _ = work.within(budget)
        taken = {str(job.row.tag) for job in inside}
    running_cost = Money.zero()
    running_saving = Money.zero()
    lines: list[JobLine] = []
    for job in ranked:
        running_cost = running_cost + job.cost
        running_saving = running_saving + job.saving
        lines.append(
            JobLine(
                tag=str(job.row.tag),
                priority=job.priority.label,
                action=job.job.action.label,
                reason=job.job.reason,
                cost=job.cost,
                saving=job.saving,
                payback=job.job.payback_years,
                cumulative_cost=running_cost,
                cumulative_saving=running_saving,
                inside_budget=budget is None or str(job.row.tag) in taken,
            )
        )
    return WorkReport(
        site=site,
        lines_in=lines,
        budget=budget,
        total_cost=running_cost,
        total_saving=running_saving,
    )
