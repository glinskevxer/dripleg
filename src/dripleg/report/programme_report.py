"""The programme report: what is due, what is late, what nobody has looked at.

Compliance is one number and it hides two very different problems. A plant that
is late on forty traps has a resourcing problem. A plant that has never looked
at forty traps has a register problem, and no amount of survey crew fixes it,
because those tags were never on a route.

So both are printed, separately, and the compliance figure is stated as what it
is: the share of the population that is neither late nor unlooked at.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.programme.schedule import Schedule
from dripleg.report.table import Column, Table

__all__ = ["ProgrammeReport", "build_programme_report"]

_MONTH_NAMES = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)


@dataclass(frozen=True)
class ProgrammeReport:
    """The survey programme, as of one day."""

    site: str
    on: dt.date
    stations: int
    due: int
    overdue: int
    never_surveyed: int
    shortened: int
    compliance: float
    late_rows: list[tuple[str, str, str, str]]
    unlooked_rows: list[tuple[str, str, str]]
    workload: dict[int, int]

    @property
    def headline(self) -> str:
        return (
            f"{self.site} as at {self.on}: {self.compliance:.1%} compliant, "
            f"{self.overdue} late and {self.never_surveyed} never surveyed"
        )

    def summary_lines(self) -> list[str]:
        return [
            f"stations        {self.stations}",
            f"due now         {self.due}",
            f"overdue         {self.overdue}",
            f"never surveyed  {self.never_surveyed}",
            f"on a short leash {self.shortened} (failed at their last survey)",
            f"compliance      {self.compliance:.1%}",
        ]

    def late_table(self) -> Table:
        table = Table(
            [Column("tag"), Column("last seen"), Column("due"), Column.number("days late")]
        )
        table.extend(self.late_rows)
        return table

    def unlooked_table(self) -> Table:
        table = Table([Column("tag"), Column("service"), Column.number("interval")])
        table.extend(self.unlooked_rows)
        return table

    def workload_table(self) -> Table:
        table = Table([Column("month"), Column.number("due")])
        for month in range(1, 13):
            table.add([_MONTH_NAMES[month - 1], self.workload.get(month, 0)])
        return table

    def lines(self) -> list[str]:
        out = [self.headline, ""]
        out.extend(self.summary_lines())
        if self.late_rows:
            out.extend(["", "overdue", ""])
            out.extend(self.late_table().lines())
        if self.unlooked_rows:
            out.extend(["", "never surveyed", ""])
            out.extend(self.unlooked_table().lines())
        out.extend(["", f"what falls due in {self.on.year + 1}", ""])
        out.extend(self.workload_table().lines())
        return out

    def render(self) -> str:
        return "\n".join(self.lines())

    def as_dict(self) -> dict[str, object]:
        return {
            "site": self.site,
            "as_at": self.on.isoformat(),
            "stations": self.stations,
            "due": self.due,
            "overdue": self.overdue,
            "never_surveyed": self.never_surveyed,
            "shortened": self.shortened,
            "compliance": round(self.compliance, 4),
            "late": [
                {"tag": tag, "last_seen": seen, "due": due, "days_late": late}
                for tag, seen, due, late in self.late_rows
            ],
            "unlooked_at": [
                {"tag": tag, "service": service, "interval_months": interval}
                for tag, service, interval in self.unlooked_rows
            ],
            "workload": {str(month): count for month, count in sorted(self.workload.items())},
        }


def build_programme_report(site: str, schedule: Schedule, on: dt.date) -> ProgrammeReport:
    late = schedule.overdue_on(on)
    unlooked = schedule.never_surveyed()
    return ProgrammeReport(
        site=site,
        on=on,
        stations=len(schedule),
        due=len(schedule.due_by(on)),
        overdue=len(late),
        never_surveyed=len(unlooked),
        shortened=len(schedule.shortened()),
        compliance=schedule.compliance_on(on),
        late_rows=[
            (
                str(entry.tag),
                entry.last_surveyed.isoformat() if entry.last_surveyed else "never",
                entry.due_on.isoformat() if entry.due_on else "",
                str(entry.days_late_on(on)),
            )
            for entry in late
        ],
        unlooked_rows=[
            (str(entry.tag), entry.station.service.label, str(entry.interval_months))
            for entry in unlooked
        ],
        workload=schedule.workload_by_month(on.year + 1),
    )
