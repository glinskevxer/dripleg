"""A route: the order a technician walks the traps in.

Order is the whole point. A route is not a set of tags, it is a walk, and the
walk is what makes a two day survey take two days instead of four. It gets
built once from the drawings and then edited every survey as valves get capped
and platforms get built, so the operations that matter are inserting a stop at
a position and dropping one without disturbing the rest.

A route is also where survey coverage is measured from. Traps that are on the
register and on no route are the ones nobody ever looks at, and they are
invisible unless something goes looking for them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dripleg.errors import ConflictError, NotFoundError, ValidationError
from dripleg.model.register import TrapRegister
from dripleg.model.tags import AreaCode, SiteCode, TrapTag

__all__ = ["Route", "unrouted_tags"]

MAX_STOPS = 400


@dataclass
class Route:
    """An ordered walk through part of a plant."""

    site: SiteCode
    code: str
    name: str
    stops: list[TrapTag] = field(default_factory=list)
    minutes_per_stop: float = 6.0
    walk_minutes: float = 30.0

    def __post_init__(self) -> None:
        cleaned = self.code.strip().upper()
        if not cleaned:
            raise ValidationError("a route needs a code", field="code")
        self.code = cleaned
        squeezed = " ".join(self.name.split())
        if not squeezed:
            raise ValidationError("a route needs a name", field="name")
        self.name = squeezed
        if self.minutes_per_stop <= 0:
            raise ValidationError("a stop takes some time", field="minutes_per_stop")
        if self.walk_minutes < 0:
            raise ValidationError("walking time is not negative", field="walk_minutes")
        seen: set[TrapTag] = set()
        for tag in self.stops:
            if tag in seen:
                raise ValidationError(f"{tag} is on this route twice", field="stops")
            seen.add(tag)
        if len(self.stops) > MAX_STOPS:
            raise ValidationError(f"a route stops at {MAX_STOPS} traps", field="stops")

    @classmethod
    def of(cls, site: str, code: str, name: str, stops: list[str] | None = None) -> Route:
        return cls(
            site=SiteCode.parse(site),
            code=code,
            name=name,
            stops=[TrapTag.parse(t) for t in stops or []],
        )

    def __len__(self) -> int:
        return len(self.stops)

    def __contains__(self, tag: object) -> bool:
        if isinstance(tag, str):
            return TrapTag.parse(tag) in self.stops
        return tag in self.stops

    @property
    def areas(self) -> list[AreaCode]:
        return sorted({tag.area for tag in self.stops})

    @property
    def estimated_minutes(self) -> float:
        return self.walk_minutes + self.minutes_per_stop * len(self.stops)

    @property
    def estimated_hours(self) -> float:
        return self.estimated_minutes / 60.0

    def position_of(self, tag: TrapTag | str) -> int:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        try:
            return self.stops.index(wanted)
        except ValueError:
            raise NotFoundError("stop", str(wanted)) from None

    def add_stop(self, tag: TrapTag | str, *, after: TrapTag | str | None = None) -> None:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        if wanted in self.stops:
            raise ConflictError(f"{wanted} is already on route {self.code}")
        if len(self.stops) >= MAX_STOPS:
            raise ValidationError(f"a route stops at {MAX_STOPS} traps", field="stops")
        if after is None:
            self.stops.append(wanted)
            return
        self.stops.insert(self.position_of(after) + 1, wanted)

    def drop_stop(self, tag: TrapTag | str) -> None:
        self.stops.pop(self.position_of(tag))

    def split(self, days: int) -> list[list[TrapTag]]:
        """Cut the walk into day sized pieces, keeping the order.

        The last piece takes the remainder rather than spreading it, because a
        technician would rather have a short last day than an uneven week.
        """

        if days < 1:
            raise ValidationError("a route is walked in at least one day", field="days")
        if not self.stops:
            return [[] for _ in range(days)]
        size = -(-len(self.stops) // days)
        pieces = [self.stops[i : i + size] for i in range(0, len(self.stops), size)]
        while len(pieces) < days:
            pieces.append([])
        return pieces

    def missing_from(self, register: TrapRegister) -> list[TrapTag]:
        """Stops on this route that are not stations any more."""

        return [tag for tag in self.stops if register.find(tag) is None]

    def __str__(self) -> str:
        return f"{self.code} {self.name} ({len(self.stops)} stops)"


def unrouted_tags(register: TrapRegister, routes: list[Route]) -> list[TrapTag]:
    """Stations that no route visits, which is the coverage hole."""

    covered = {tag for route in routes for tag in route.stops}
    return [station.tag for station in register if station.tag not in covered]
