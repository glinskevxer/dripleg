"""Two surveys, rendered side by side, with the unfixed traps named.

The block at the bottom is the reason this report exists. Everything above it
is a scoreboard, and a scoreboard is read once and filed. The list of traps
that failed twice running, with what each has cost over the two cycles, is the
part somebody acts on, because every one of those is a job that was raised and
did not happen.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.programme.trend import Trend
from dripleg.report.table import Column, Table
from dripleg.units.money import Money

__all__ = ["TrendReport", "build_trend_report"]


@dataclass(frozen=True)
class TrendReport:
    """A comparison of two surveys, ready to print."""

    earlier: str
    later: str
    compared: int
    counts: dict[str, int]
    failure_rate_before: float
    failure_rate_after: float
    cost_before: Money
    cost_after: Money
    unfixed_cost: Money
    unfixed_rows: list[tuple[str, str, str]]
    only_earlier: list[str]
    only_later: list[str]

    @property
    def saving(self) -> Money:
        return self.cost_before - self.cost_after

    @property
    def is_improving(self) -> bool:
        return self.failure_rate_after < self.failure_rate_before

    @property
    def direction(self) -> str:
        """Down, up or flat. Flat is its own answer, not a rounding of up."""

        if self.failure_rate_after < self.failure_rate_before:
            return "down"
        if self.failure_rate_after > self.failure_rate_before:
            return "up"
        return "flat"

    @property
    def headline(self) -> str:
        if self.direction == "flat":
            return (
                f"{self.earlier} to {self.later}: failure rate flat at "
                f"{self.failure_rate_after:.1%} over {self.compared} traps"
            )
        return (
            f"{self.earlier} to {self.later}: failure rate {self.direction} from "
            f"{self.failure_rate_before:.1%} to {self.failure_rate_after:.1%} "
            f"over {self.compared} traps"
        )

    def summary_lines(self) -> list[str]:
        return [
            f"fixed           {self.counts['fixed']}",
            f"still failing   {self.counts['still failing']}",
            f"newly failed    {self.counts['newly failed']}",
            f"unchanged       {self.counts['unchanged']}",
            f"cost before     {self.cost_before}",
            f"cost after      {self.cost_after}",
            f"movement        {self.saving} a year",
            f"still costing   {self.unfixed_cost} on traps that failed twice",
        ]

    def unfixed_table(self) -> Table:
        table = Table([Column("tag"), Column("condition"), Column.number("a year")])
        table.extend(self.unfixed_rows)
        return table

    def lines(self) -> list[str]:
        out = [self.headline, ""]
        out.extend(self.summary_lines())
        if self.unfixed_rows:
            out.extend(["", "failed at both surveys", ""])
            out.extend(self.unfixed_table().lines())
        if self.only_later:
            out.extend(["", "read this time and not last: " + ", ".join(self.only_later)])
        if self.only_earlier:
            out.extend(["", "read last time and not this: " + ", ".join(self.only_earlier)])
        return out

    def render(self) -> str:
        return "\n".join(self.lines())

    def as_dict(self) -> dict[str, object]:
        return {
            "earlier": self.earlier,
            "later": self.later,
            "compared": self.compared,
            "direction": self.direction,
            "counts": dict(self.counts),
            "failure_rate_before": round(self.failure_rate_before, 4),
            "failure_rate_after": round(self.failure_rate_after, 4),
            "cost_before_cents": self.cost_before.cents,
            "cost_after_cents": self.cost_after.cents,
            "saving_cents": self.saving.cents,
            "unfixed_cost_cents": self.unfixed_cost.cents,
            "unfixed": [
                {"tag": tag, "condition": condition, "annual": cost}
                for tag, condition, cost in self.unfixed_rows
            ],
            "only_earlier": list(self.only_earlier),
            "only_later": list(self.only_later),
        }


def build_trend_report(trend: Trend) -> TrendReport:
    return TrendReport(
        earlier=trend.earlier,
        later=trend.later,
        compared=trend.compared,
        counts=trend.counts(),
        failure_rate_before=trend.failure_rate_before,
        failure_rate_after=trend.failure_rate_after,
        cost_before=trend.cost_before,
        cost_after=trend.cost_after,
        unfixed_cost=trend.unfixed_cost,
        unfixed_rows=[
            (str(m.tag), m.after.label, str(m.cost_after))
            for m in sorted(
                trend.in_bucket("still failing"),
                key=lambda m: (-m.cost_after.cents, str(m.tag)),
            )
        ],
        only_earlier=[str(t) for t in trend.only_earlier],
        only_later=[str(t) for t in trend.only_later],
    )
