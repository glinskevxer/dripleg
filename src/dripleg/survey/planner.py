"""Building routes out of a register that has never had any.

A plant arriving with four thousand tags and no routes needs a first cut, and
the first cut does not have to be good. It has to be walkable and it has to
cover everything, because a technician can reorder stops in the field and
cannot survey a trap nobody put on a route.

So the planner groups by area, then by system inside the area, then walks the
tags in sequence order, which is roughly the order they were tagged in and
therefore roughly the order they sit along the pipe. Then it cuts the result
into routes that fit a shift.

What it deliberately does not do is optimise. There is no travel matrix here,
no distances, and no attempt to solve anything: the drawing office knows the
plant and this does not, and a route that looks clever and sends somebody up
and down the same stair four times destroys the crew's trust in the tool.
"""

from __future__ import annotations

from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.attributes import Accessibility
from dripleg.model.register import TrapRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.survey.route import Route

__all__ = ["PlannedRoutes", "needs_arranging", "permit_stations", "plan_routes"]

DEFAULT_SHIFT_HOURS = 7.0


@dataclass(frozen=True)
class PlannedRoutes:
    """A first cut at routing a register."""

    routes: list[Route]
    set_aside: list[TrapTag]

    @property
    def covered(self) -> int:
        return sum(len(route) for route in self.routes)

    @property
    def hours(self) -> float:
        return sum(route.estimated_hours for route in self.routes)

    def __len__(self) -> int:
        return len(self.routes)

    def __str__(self) -> str:
        return (
            f"{len(self.routes)} routes covering {self.covered} traps in "
            f"{self.hours:.1f} hours, {len(self.set_aside)} set aside"
        )


def plan_routes(
    register: TrapRegister,
    site: SiteCode | str,
    *,
    shift_hours: float = DEFAULT_SHIFT_HOURS,
    minutes_per_stop: float = 6.0,
    walk_minutes: float = 30.0,
    prefix: str = "R",
) -> PlannedRoutes:
    """Cut a register into shift sized walks, area by area.

    Stations that need arranging beforehand are set aside rather than dropped
    into an ordinary route: a scaffold job on stop eleven stops the whole day,
    and those are planned separately.
    """

    if shift_hours <= 0:
        raise ValidationError("a shift is longer than nothing", field="shift_hours")
    if minutes_per_stop <= 0:
        raise ValidationError("a stop takes some time", field="minutes_per_stop")
    per_route = int((shift_hours * 60.0 - walk_minutes) // minutes_per_stop)
    if per_route < 1:
        raise ValidationError(
            "the walk alone fills the shift, so no stops fit on a route",
            field="shift_hours",
        )
    site_code = site if isinstance(site, SiteCode) else SiteCode.parse(site)
    grouped: dict[tuple[str, str], list[TrapTag]] = {}
    set_aside: list[TrapTag] = []
    for station in register:
        if not station.accessibility.surveyable_on_a_normal_route:
            set_aside.append(station.tag)
            continue
        key = (station.tag.area.value, station.tag.system.value)
        grouped.setdefault(key, []).append(station.tag)
    routes: list[Route] = []
    number = 0
    for (area, system), tags in sorted(grouped.items()):
        ordered = sorted(tags)
        for start in range(0, len(ordered), per_route):
            number += 1
            piece = ordered[start : start + per_route]
            part = "" if len(ordered) <= per_route else f" part {start // per_route + 1}"
            routes.append(
                Route(
                    site=site_code,
                    code=f"{prefix}{number:02d}",
                    name=f"{area} {system}{part}",
                    stops=list(piece),
                    minutes_per_stop=minutes_per_stop,
                    walk_minutes=walk_minutes,
                )
            )
    return PlannedRoutes(routes=routes, set_aside=sorted(set_aside))


def needs_arranging(register: TrapRegister) -> list[TrapTag]:
    """Stations a technician cannot simply walk up to."""

    return sorted(
        station.tag
        for station in register
        if not station.accessibility.surveyable_on_a_normal_route
    )


def permit_stations(register: TrapRegister) -> dict[Accessibility, list[TrapTag]]:
    """The set aside stations, grouped by what has to be arranged."""

    grouped: dict[Accessibility, list[TrapTag]] = {}
    for station in register:
        if station.accessibility.surveyable_on_a_normal_route:
            continue
        grouped.setdefault(station.accessibility, []).append(station.tag)
    return {
        access: sorted(tags)
        for access, tags in sorted(grouped.items(), key=lambda pair: pair[0].value)
    }
