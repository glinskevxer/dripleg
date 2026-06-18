"""One page on the whole programme, which is what gets read at the review.

Everything else in this package answers one question well. This answers the six
that get asked in the meeting, on one page, with the awkward ones on it rather
than left out:

- how much of the population did we actually look at
- how many of what we looked at were failing
- what is that costing a year
- how much of last year's work got done
- what is the backlog costing while it waits
- how far behind is the survey programme itself

The last two are the ones a contractor's own report never carries, because they
are both measures of whether the plant acted, not of whether the survey was
good. They are here for exactly that reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.report.base import Rendered
from dripleg.report.table import Column, Table
from dripleg.units.money import Money

__all__ = [
    "ScoreLine",
    "Scorecard",
]


@dataclass(frozen=True)
class ScoreLine:
    """One number on the scorecard, with what it should be next to it."""

    name: str
    value: str
    target: str = ""
    note: str = ""

    @property
    def has_target(self) -> bool:
        return bool(self.target.strip())

    def __str__(self) -> str:
        if self.has_target:
            return f"{self.name}: {self.value} (target {self.target})"
        return f"{self.name}: {self.value}"


@dataclass(frozen=True)
class Scorecard(Rendered):
    """The programme on one page."""

    site: str
    as_at: str
    survey: str
    lines_in: list[ScoreLine]

    @property
    def headline(self) -> str:
        return f"{self.site} steam trap programme as at {self.as_at} ({self.survey})"

    def table(self) -> Table:
        table = Table(
            [
                Column("measure"),
                Column.number("this year"),
                Column.number("target"),
                Column("note", max_width=44),
            ]
        )
        for line in self.lines_in:
            table.add([line.name, line.value, line.target, line.note])
        return table

    def lines(self) -> list[str]:
        return [self.headline, "", *self.table().lines()]

    def as_dict(self) -> dict[str, object]:
        return {
            "site": self.site,
            "as_at": self.as_at,
            "survey": self.survey,
            "measures": [
                {
                    "name": line.name,
                    "value": line.value,
                    "target": line.target,
                    "note": line.note,
                }
                for line in self.lines_in
            ],
        }

    def find(self, name: str) -> ScoreLine | None:
        for line in self.lines_in:
            if line.name == name:
                return line
        return None


def build_scorecard(
    site: str,
    as_at: str,
    survey: str,
    *,
    coverage: float,
    failure_rate: float,
    annual_cost: Money,
    jobs_raised: int,
    jobs_verified: int,
    backlog_cost: Money,
    programme_compliance: float,
    never_surveyed: int,
) -> Scorecard:
    """Assemble the six numbers, with the targets this standard works to."""

    done = 0.0 if jobs_raised == 0 else jobs_verified / jobs_raised
    return Scorecard(
        site=site,
        as_at=as_at,
        survey=survey,
        lines_in=[
            ScoreLine(
                "survey coverage",
                f"{coverage:.1%}",
                "95%",
                "of the live population actually assessed",
            ),
            ScoreLine(
                "failure rate",
                f"{failure_rate:.1%}",
                "under 10%",
                "of what was assessed, not of what was read",
            ),
            ScoreLine(
                "annual loss",
                str(annual_cost),
                "",
                "fuel, makeup, effluent and treatment chemical",
            ),
            ScoreLine(
                "work completed",
                f"{done:.1%}",
                "90%",
                f"{jobs_verified} of {jobs_raised} jobs verified on a retest",
            ),
            ScoreLine(
                "backlog accrual",
                str(backlog_cost),
                "",
                "what the open jobs have cost since they were found",
            ),
            ScoreLine(
                "programme compliance",
                f"{programme_compliance:.1%}",
                "95%",
                f"{never_surveyed} stations have never been surveyed",
            ),
        ],
    )
