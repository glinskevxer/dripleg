"""Turning whatever a caller handed in into the key type the book wants.

Every repository method takes a site as a `SiteCode` or a string, because the
command line has strings and the model has codes and neither should have to
know about the other. That coercion was written out in place thirty times
before this module existed, and the thirty-first was going to be the one that
forgot to normalise the case.

The date helpers are here for the same reason. A date comes out of sqlite as
text, and every repository was doing its own `dt.date.fromisoformat` with its
own idea of what to do with a null.
"""

from __future__ import annotations

import datetime as dt

from dripleg.model.tags import AreaCode, SiteCode, SystemCode, TrapTag

__all__ = ["as_area", "as_date", "as_site", "as_system", "as_tag", "maybe_date"]


def as_site(site: SiteCode | str) -> SiteCode:
    return site if isinstance(site, SiteCode) else SiteCode.parse(site)


def as_area(area: AreaCode | str) -> AreaCode:
    return area if isinstance(area, AreaCode) else AreaCode.parse(area)


def as_system(system: SystemCode | str) -> SystemCode:
    return system if isinstance(system, SystemCode) else SystemCode.parse(system)


def as_tag(tag: TrapTag | str) -> TrapTag:
    return tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)


def as_date(value: object) -> dt.date:
    """A date column that the schema says is never null."""

    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def maybe_date(value: object) -> dt.date | None:
    """A date column that the schema says may be null."""

    return None if value is None else as_date(value)
