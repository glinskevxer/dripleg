"""How many hours a year the leg is actually live.

This is the quietest way a loss report gets wrong by a factor of three. A trap
on a process coil that runs continuously loses steam for 8,760 hours. A trap on
a building heating main loses it for the heating season and nothing at all in
July, and a tracer on a summer shutdown line loses it for whatever the campaign
was. Multiplying every leak by a full year is the default that flatters the
contractor and gets the report thrown out at the first review meeting.

So the profile is an object on the installation, not a constant in the loss
engine, and it can answer for a whole year or for the slice of a year a report
covers.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

from dripleg.errors import ValidationError
from dripleg.model.calendar import DateRange
from dripleg.units.flow import HOURS_PER_YEAR

__all__ = ["OperatingProfile", "ServicePattern"]

_HOURS_PER_DAY = 24.0


class ServicePattern(Enum):
    """The shape of the year, before the load factor is applied."""

    CONTINUOUS = "continuous"
    HEATING_SEASON = "heating_season"
    COOLING_SEASON = "cooling_season"
    CAMPAIGN = "campaign"
    INTERMITTENT = "intermittent"

    @property
    def is_seasonal(self) -> bool:
        return self in {
            ServicePattern.HEATING_SEASON,
            ServicePattern.COOLING_SEASON,
            ServicePattern.CAMPAIGN,
        }


# Months a pattern is live in, as month numbers. A campaign carries its own.
_SEASON_MONTHS: dict[ServicePattern, frozenset[int]] = {
    ServicePattern.CONTINUOUS: frozenset(range(1, 13)),
    ServicePattern.INTERMITTENT: frozenset(range(1, 13)),
    ServicePattern.HEATING_SEASON: frozenset({10, 11, 12, 1, 2, 3, 4}),
    ServicePattern.COOLING_SEASON: frozenset({5, 6, 7, 8, 9}),
}


@dataclass(frozen=True)
class OperatingProfile:
    """When a steam line is live, and how hard.

    `load_factor` is not a duty cycle on the trap. It is the fraction of the
    live hours the line actually carries steam, which is how an intermittent
    tracer or a batch reactor gets counted honestly.
    """

    code: str
    name: str
    pattern: ServicePattern = ServicePattern.CONTINUOUS
    load_factor: float = 1.0
    campaign_months: frozenset[int] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValidationError("an operating profile needs a code", field="code")
        if not self.name.strip():
            raise ValidationError("an operating profile needs a name", field="name")
        if not 0.0 < self.load_factor <= 1.0:
            raise ValidationError(
                f"load factor sits in (0, 1], got {self.load_factor:g}",
                field="load_factor",
            )
        if self.pattern is ServicePattern.CAMPAIGN:
            if not self.campaign_months:
                raise ValidationError("a campaign has to say which months", field="campaign_months")
            if any(m < 1 or m > 12 for m in self.campaign_months):
                raise ValidationError("campaign months are month numbers", field="campaign_months")
        elif self.campaign_months:
            raise ValidationError(
                "only a campaign profile carries its own months",
                field="campaign_months",
            )

    @classmethod
    def continuous(cls, code: str = "CONT", name: str = "Continuous") -> OperatingProfile:
        return cls(code=code, name=name, pattern=ServicePattern.CONTINUOUS)

    @property
    def live_months(self) -> frozenset[int]:
        if self.pattern is ServicePattern.CAMPAIGN:
            return self.campaign_months
        return _SEASON_MONTHS[self.pattern]

    def is_live_in(self, month: int) -> bool:
        if not 1 <= month <= 12:
            raise ValidationError("that is not a month number", field="month")
        return month in self.live_months

    def annual_hours(self) -> float:
        """Hours a year this line carries steam, load factor included."""

        share = len(self.live_months) / 12.0
        return HOURS_PER_YEAR * share * self.load_factor

    def hours_in(self, span: DateRange) -> float:
        """Live hours inside a reporting window, counted day by day.

        Day by day rather than by the month share, because a report that runs
        from the middle of March to the middle of May straddles the end of the
        heating season and the month share cannot see that.
        """

        if span.is_empty:
            return 0.0
        live = self.live_months
        day = span.start
        counted = 0
        while day < span.end:
            if day.month in live:
                counted += 1
            day += dt.timedelta(days=1)
        return counted * _HOURS_PER_DAY * self.load_factor

    def __str__(self) -> str:
        return f"{self.code} ({self.annual_hours():,.0f} h/y)"
