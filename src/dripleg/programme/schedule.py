"""When each trap is next due, and what that says about the programme.

Two rules decide a due date and they interact, which is the whole reason this
is a module rather than a column.

The first is the interval: a drip trap is looked at every twelve months, a
turbine drain every six, and a station can carry its own override. The second
is the failure rule: a trap that failed at its last survey is looked at again
inside a quarter regardless of its class, because a trap that has failed once
is far likelier than average to fail again and because somebody is supposed to
have repaired it.

A trap with no survey history at all is not simply overdue. It has never been
looked at, and that is a different report with a different remedy, so the two
are counted separately.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.calendar import add_months
from dripleg.model.installation import TrapInstallation
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition

__all__ = ["AFTER_FAILURE_MONTHS", "DueEntry", "Schedule", "build_schedule"]

AFTER_FAILURE_MONTHS = 3
"""How soon a failed trap comes round again, whatever its service class says."""


@dataclass(frozen=True)
class DueEntry:
    """One trap's place in the programme."""

    station: TrapInstallation
    last_surveyed: dt.date | None
    last_condition: TrapCondition | None
    due_on: dt.date | None
    interval_months: int

    @property
    def tag(self) -> TrapTag:
        return self.station.tag

    @property
    def never_surveyed(self) -> bool:
        return self.last_surveyed is None

    def is_due_by(self, day: dt.date) -> bool:
        if self.due_on is None:
            return True
        return day >= self.due_on

    def is_overdue_on(self, day: dt.date) -> bool:
        """Late, as opposed to never looked at, which is counted separately."""

        return self.due_on is not None and day > self.due_on

    def days_late_on(self, day: dt.date) -> int:
        if self.due_on is None or day <= self.due_on:
            return 0
        return (day - self.due_on).days

    @property
    def shortened_after_failure(self) -> bool:
        return (
            self.last_condition is not None
            and self.last_condition.is_failure
            and self.interval_months == AFTER_FAILURE_MONTHS
        )

    def __str__(self) -> str:
        if self.due_on is None:
            return f"{self.tag} never surveyed"
        return f"{self.tag} due {self.due_on} ({self.interval_months} month interval)"


def _interval_for(station: TrapInstallation, condition: TrapCondition | None) -> int:
    if condition is not None and condition.is_failure:
        return min(AFTER_FAILURE_MONTHS, station.survey_interval_months)
    return station.survey_interval_months


class Schedule:
    """Every station's due date, and the questions asked of the set."""

    def __init__(self, entries: list[DueEntry]) -> None:
        self.entries = sorted(entries, key=lambda e: (e.due_on or dt.date.min, str(e.tag)))

    def __len__(self) -> int:
        return len(self.entries)

    def find(self, tag: TrapTag | str) -> DueEntry | None:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        for entry in self.entries:
            if entry.tag == wanted:
                return entry
        return None

    def never_surveyed(self) -> list[DueEntry]:
        return [entry for entry in self.entries if entry.never_surveyed]

    def due_by(self, day: dt.date) -> list[DueEntry]:
        return [entry for entry in self.entries if entry.is_due_by(day)]

    def overdue_on(self, day: dt.date) -> list[DueEntry]:
        late = [entry for entry in self.entries if entry.is_overdue_on(day)]
        return sorted(late, key=lambda e: (-e.days_late_on(day), str(e.tag)))

    def shortened(self) -> list[DueEntry]:
        return [entry for entry in self.entries if entry.shortened_after_failure]

    def in_window(self, start: dt.date, end: dt.date) -> list[DueEntry]:
        if end < start:
            raise ValidationError("a window ends after it starts", field="end")
        return [
            entry
            for entry in self.entries
            if entry.due_on is not None and start <= entry.due_on < end
        ]

    def compliance_on(self, day: dt.date) -> float:
        """Share of the population that is not late and not unlooked at."""

        if not self.entries:
            return 1.0
        behind = len(self.overdue_on(day)) + len(self.never_surveyed())
        return max(0.0, 1.0 - behind / len(self.entries))

    def workload_by_month(self, year: int) -> dict[int, int]:
        """How many traps fall due in each month of a year."""

        counts = {month: 0 for month in range(1, 13)}
        for entry in self.entries:
            if entry.due_on is not None and entry.due_on.year == year:
                counts[entry.due_on.month] += 1
        return counts

    def __str__(self) -> str:
        return f"{len(self.entries)} stations, {len(self.never_surveyed())} never surveyed"


def build_schedule(
    register: TrapRegister,
    history: dict[TrapTag, tuple[dt.date, TrapCondition]],
    *,
    on: dt.date,
) -> Schedule:
    """Work out every live station's due date from what it was last found to be."""

    entries: list[DueEntry] = []
    for station in register.in_service_on(on):
        last = history.get(station.tag)
        if last is None:
            entries.append(
                DueEntry(
                    station=station,
                    last_surveyed=None,
                    last_condition=None,
                    due_on=None,
                    interval_months=station.survey_interval_months,
                )
            )
            continue
        surveyed_on, condition = last
        months = _interval_for(station, condition)
        entries.append(
            DueEntry(
                station=station,
                last_surveyed=surveyed_on,
                last_condition=condition,
                due_on=add_months(surveyed_on, months),
                interval_months=months,
            )
        )
    return Schedule(entries)
