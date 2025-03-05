"""The population: every trap station at a site, and how to ask about them.

This is deliberately an in memory collection over a list of installations and
not a database query layer. The store hydrates one of these, the analysis code
walks it, and neither of them has to know anything about the other. It also
means the whole of the diagnosis and loss layer can be tested against a
register built by hand in four lines.

Stations are keyed on tag within a site. A tag reused after a station is
demolished is the same station as far as this is concerned, which is the
convention the drawing office works to.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator

from dripleg.errors import ConflictError, NotFoundError
from dripleg.model.attributes import Criticality, ServiceType
from dripleg.model.header import SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.tags import AreaCode, SystemCode, TrapTag

__all__ = ["TrapRegister"]


class TrapRegister:
    """Every trap station at one site."""

    def __init__(self, installations: Iterable[TrapInstallation] = ()) -> None:
        self._by_tag: dict[TrapTag, TrapInstallation] = {}
        for installation in installations:
            self.add(installation)

    def add(self, installation: TrapInstallation) -> None:
        if installation.tag in self._by_tag:
            raise ConflictError(f"{installation.tag} is already on the register")
        self._by_tag[installation.tag] = installation

    def replace(self, installation: TrapInstallation) -> None:
        """Put back a station that has been changed, which is how a work order
        and a retirement both land."""

        if installation.tag not in self._by_tag:
            raise NotFoundError("trap station", str(installation.tag))
        self._by_tag[installation.tag] = installation

    def get(self, tag: TrapTag | str) -> TrapInstallation:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        try:
            return self._by_tag[wanted]
        except KeyError:
            raise NotFoundError("trap station", str(wanted)) from None

    def find(self, tag: TrapTag | str) -> TrapInstallation | None:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        return self._by_tag.get(wanted)

    def __len__(self) -> int:
        return len(self._by_tag)

    def __contains__(self, tag: object) -> bool:
        if isinstance(tag, str):
            return TrapTag.parse(tag) in self._by_tag
        return tag in self._by_tag

    def __iter__(self) -> Iterator[TrapInstallation]:
        return iter(sorted(self._by_tag.values(), key=lambda i: i.tag))

    @property
    def tags(self) -> list[TrapTag]:
        return sorted(self._by_tag)

    def in_service_on(self, day: dt.date) -> list[TrapInstallation]:
        return [i for i in self if i.is_in_service_on(day)]

    def in_area(self, area: AreaCode | str) -> list[TrapInstallation]:
        wanted = area if isinstance(area, AreaCode) else AreaCode.parse(area)
        return [i for i in self if i.tag.area == wanted]

    def on_system(self, area: AreaCode | str, system: SystemCode | str) -> list[TrapInstallation]:
        wanted_area = area if isinstance(area, AreaCode) else AreaCode.parse(area)
        wanted_system = system if isinstance(system, SystemCode) else SystemCode.parse(system)
        return [i for i in self if i.tag.area == wanted_area and i.tag.system == wanted_system]

    def on_header(self, header: SteamHeader) -> list[TrapInstallation]:
        return [i for i in self if i.header.key == header.key]

    def with_service(self, service: ServiceType) -> list[TrapInstallation]:
        return [i for i in self if i.service is service]

    def with_criticality(self, criticality: Criticality) -> list[TrapInstallation]:
        return [i for i in self if i.criticality is criticality]

    def areas(self) -> list[AreaCode]:
        return sorted({i.tag.area for i in self._by_tag.values()})

    def headers(self) -> list[SteamHeader]:
        seen: dict[tuple[str, str, str], SteamHeader] = {}
        for installation in self:
            seen.setdefault(installation.header.key, installation.header)
        return [seen[key] for key in sorted(seen)]

    def count_by_area(self, on: dt.date | None = None) -> dict[AreaCode, int]:
        source = self.in_service_on(on) if on is not None else list(self)
        counts: dict[AreaCode, int] = {}
        for installation in source:
            counts[installation.tag.area] = counts.get(installation.tag.area, 0) + 1
        return dict(sorted(counts.items()))

    def count_by_service(self, on: dt.date | None = None) -> dict[ServiceType, int]:
        source = self.in_service_on(on) if on is not None else list(self)
        counts: dict[ServiceType, int] = {}
        for installation in source:
            counts[installation.service] = counts.get(installation.service, 0) + 1
        return dict(sorted(counts.items(), key=lambda pair: pair[0].value))

    def next_tag_on(self, area: AreaCode | str, system: SystemCode | str) -> TrapTag:
        """The tag a new station on this system would get."""

        existing = self.on_system(area, system)
        wanted_area = area if isinstance(area, AreaCode) else AreaCode.parse(area)
        wanted_system = system if isinstance(system, SystemCode) else SystemCode.parse(system)
        if not existing:
            return TrapTag(wanted_area, wanted_system, 1)
        return max(i.tag for i in existing).next_in_sequence()
