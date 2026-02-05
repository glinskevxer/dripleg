"""What a known failure has cost since somebody was told about it.

An annual loss figure is an argument for doing the work. An accrued figure is
an argument for doing it this week, and it is the only number in this package
that goes up on its own while nobody looks at it.

The arithmetic is not the annual cost divided by 365. A leg that only runs in
the heating season accrues nothing in July, and a leg on a campaign accrues
nothing between campaigns, so the accrual walks the operating profile over the
window the same way the annual figure walks it over a year.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.calendar import DateRange
from dripleg.model.installation import TrapInstallation
from dripleg.model.tags import TrapTag
from dripleg.units.flow import Mass
from dripleg.units.money import Money

__all__ = ["Accrual", "accrue", "accrue_all"]


@dataclass(frozen=True)
class Accrual:
    """One failure, and what it has cost since it was found."""

    tag: TrapTag
    found_on: dt.date
    as_at: dt.date
    live_hours: float
    annual_hours: float
    annual_cost: Money
    pounds_per_hour: float

    def __post_init__(self) -> None:
        if self.as_at < self.found_on:
            raise ValidationError("nothing accrues before it was found", field="as_at")
        if self.annual_hours <= 0:
            raise ValidationError("a leg with no live hours accrues nothing", field="annual_hours")

    @property
    def days(self) -> int:
        return (self.as_at - self.found_on).days

    @property
    def share_of_a_year(self) -> float:
        return self.live_hours / self.annual_hours

    @property
    def cost(self) -> Money:
        return self.annual_cost.scaled(self.share_of_a_year)

    @property
    def steam(self) -> Mass:
        return Mass.from_pounds(self.pounds_per_hour * self.live_hours)

    @property
    def is_material(self) -> bool:
        return self.cost.cents > 0

    def __str__(self) -> str:
        return f"{self.tag} has cost {self.cost} in the {self.days} days since {self.found_on}"


def accrue(
    station: TrapInstallation,
    *,
    found_on: dt.date,
    as_at: dt.date,
    annual_cost: Money,
    pounds_per_hour: float,
) -> Accrual:
    """Walk one station's operating profile from the finding to today."""

    if as_at < found_on:
        raise ValidationError("nothing accrues before it was found", field="as_at")
    window = DateRange(found_on, as_at + dt.timedelta(days=1))
    return Accrual(
        tag=station.tag,
        found_on=found_on,
        as_at=as_at,
        live_hours=station.profile.hours_in(window),
        annual_hours=station.profile.annual_hours(),
        annual_cost=annual_cost,
        pounds_per_hour=pounds_per_hour,
    )


def accrue_all(
    entries: list[tuple[TrapInstallation, dt.date, Money, float]],
    *,
    as_at: dt.date,
) -> list[Accrual]:
    """Accrue a whole backlog, dearest first."""

    accruals = [
        accrue(
            station,
            found_on=found_on,
            as_at=as_at,
            annual_cost=annual_cost,
            pounds_per_hour=pounds_per_hour,
        )
        for station, found_on, annual_cost, pounds_per_hour in entries
        if as_at >= found_on
    ]
    return sorted(accruals, key=lambda a: (-a.cost.cents, str(a.tag)))
