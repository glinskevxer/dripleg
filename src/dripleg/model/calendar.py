"""Dates, half open ranges, and the programme year a survey belongs to.

Every date range in this package is half open: the start day is in and the end
day is not. It is the only convention where two ranges that touch neither
overlap nor leave a gap, and a survey programme is full of ranges that touch.

The programme year is not the calendar year. A contractor's survey season runs
from whenever the site says it does, usually the start of the fiscal year, and
a trap surveyed in the last week of one season is not due again in the first
week of the next.
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ValidationError

__all__ = [
    "DateRange",
    "ProgrammeYear",
    "add_months",
    "months_between",
]


def add_months(day: dt.date, months: int) -> dt.date:
    """Move a date by whole months, clamping at the end of a short month.

    The 31st of January plus one month is the 28th of February, and plus two is
    the 31st of March. Rolling into the next month instead puts a due date in
    the wrong programme year once a year, every year.
    """

    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day.day, last))


def months_between(start: dt.date, end: dt.date) -> int:
    """Whole months from one date to another, rounded toward zero."""

    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1 if months > 0 else 0
    elif months < 0 and end.day > start.day:
        months += 1
    return months


@dataclass(frozen=True, order=True)
class DateRange:
    """Half open: `start` is in the range, `end` is not."""

    start: dt.date
    end: dt.date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValidationError(
                f"a range ends after it starts, got {self.start} to {self.end}",
                field="range",
            )

    @classmethod
    def of_day(cls, day: dt.date) -> DateRange:
        return cls(day, day + dt.timedelta(days=1))

    @classmethod
    def of_year(cls, year: int) -> DateRange:
        return cls(dt.date(year, 1, 1), dt.date(year + 1, 1, 1))

    @classmethod
    def of_months(cls, start: dt.date, months: int) -> DateRange:
        if months < 0:
            raise ValidationError("a range cannot run backwards in months", field="range")
        return cls(start, add_months(start, months))

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    @property
    def is_empty(self) -> bool:
        return self.start == self.end

    @property
    def last_day(self) -> dt.date:
        """The last day actually in the range, for printing to a human."""

        if self.is_empty:
            raise ValidationError("an empty range has no last day", field="range")
        return self.end - dt.timedelta(days=1)

    def covers(self, day: dt.date) -> bool:
        return self.start <= day < self.end

    def overlaps(self, other: DateRange) -> bool:
        return self.start < other.end and other.start < self.end

    def intersection(self, other: DateRange) -> DateRange | None:
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if end <= start:
            return None
        return DateRange(start, end)

    def clipped_to(self, other: DateRange) -> DateRange:
        found = self.intersection(other)
        if found is None:
            return DateRange(other.start, other.start)
        return found

    def __str__(self) -> str:
        if self.is_empty:
            return f"{self.start} (empty)"
        return f"{self.start} to {self.last_day}"


@dataclass(frozen=True, order=True)
class ProgrammeYear:
    """A survey season, named by the calendar year it starts in."""

    starting_year: int
    start_month: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.start_month <= 12:
            raise ValidationError(
                f"a programme year starts in a month, got {self.start_month}",
                field="programme_year",
            )
        if not 1900 <= self.starting_year <= 2200:
            raise ValidationError("that is not a plausible year", field="programme_year")

    @classmethod
    def containing(cls, day: dt.date, start_month: int = 1) -> ProgrammeYear:
        if not 1 <= start_month <= 12:
            raise ValidationError("a programme year starts in a month", field="programme_year")
        year = day.year if day.month >= start_month else day.year - 1
        return cls(year, start_month)

    @property
    def range(self) -> DateRange:
        start = dt.date(self.starting_year, self.start_month, 1)
        return DateRange(start, add_months(start, 12))

    @property
    def label(self) -> str:
        if self.start_month == 1:
            return str(self.starting_year)
        return f"{self.starting_year}/{(self.starting_year + 1) % 100:02d}"

    def covers(self, day: dt.date) -> bool:
        return self.range.covers(day)

    def next(self) -> ProgrammeYear:
        return ProgrammeYear(self.starting_year + 1, self.start_month)

    def previous(self) -> ProgrammeYear:
        return ProgrammeYear(self.starting_year - 1, self.start_month)

    def __str__(self) -> str:
        return self.label
