"""Tag numbers, which are the only thing everybody at a plant agrees on.

A trap tag is stamped on a brass disc wired to the trap and written on every
piece of paper that trap ever appears on. It has structure: the area it is in,
the steam system it hangs off, and a sequence inside that. Parsing it rather
than treating it as an opaque string is what lets a report group by area
without a lookup table, and what catches the technician who wrote down a tag
from the wrong unit.

The separator is a hyphen, the parts are upper case, and the sequence is zero
padded to four places on the way out and not on the way in, because the field
tablet drops the padding and the drawing office does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dripleg.errors import ValidationError

__all__ = ["AreaCode", "SiteCode", "SystemCode", "TrapTag"]

_SITE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")
_AREA = re.compile(r"^[A-Z][A-Z0-9]{0,5}$")
_SYSTEM = re.compile(r"^[A-Z][A-Z0-9]{0,5}$")
_TAG = re.compile(
    r"^(?P<area>[A-Z][A-Z0-9]{0,5})-(?P<system>[A-Z][A-Z0-9]{0,5})-(?P<seq>[0-9]{1,6})$"
)

SEQUENCE_WIDTH = 4
MAX_SEQUENCE = 999999


def _normalise(text: str, field: str) -> str:
    cleaned = text.strip().upper().replace(" ", "")
    if not cleaned:
        raise ValidationError(f"{field} cannot be blank", field=field)
    return cleaned


@dataclass(frozen=True, order=True)
class SiteCode:
    """A plant. One database holds several, and they do not share tag numbers."""

    value: str

    def __post_init__(self) -> None:
        if not _SITE.match(self.value):
            raise ValidationError(
                f"{self.value!r} is not a site code: letters and digits, starts with a letter",
                field="site",
            )

    @classmethod
    def parse(cls, text: str) -> SiteCode:
        return cls(_normalise(text, "site"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class AreaCode:
    """A unit or block inside a plant, which is how a survey route is cut up."""

    value: str

    def __post_init__(self) -> None:
        if not _AREA.match(self.value):
            raise ValidationError(f"{self.value!r} is not an area code", field="area")

    @classmethod
    def parse(cls, text: str) -> AreaCode:
        return cls(_normalise(text, "area"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class SystemCode:
    """A steam system: the header class a trap hangs off, spelled the local way."""

    value: str

    def __post_init__(self) -> None:
        if not _SYSTEM.match(self.value):
            raise ValidationError(f"{self.value!r} is not a system code", field="system")

    @classmethod
    def parse(cls, text: str) -> SystemCode:
        return cls(_normalise(text, "system"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class TrapTag:
    """The number stamped on the disc wired to the trap."""

    area: AreaCode
    system: SystemCode
    sequence: int

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValidationError("a tag sequence starts at one", field="tag")
        if self.sequence > MAX_SEQUENCE:
            raise ValidationError(
                f"a tag sequence stops at {MAX_SEQUENCE}, got {self.sequence}",
                field="tag",
            )

    @classmethod
    def parse(cls, text: str) -> TrapTag:
        """Read a tag off a tablet export, a drawing or a spreadsheet cell."""

        cleaned = _normalise(text, "tag").replace("_", "-").replace("/", "-")
        match = _TAG.match(cleaned)
        if match is None:
            raise ValidationError(f"{text!r} is not a trap tag", field="tag")
        return cls(
            area=AreaCode(match.group("area")),
            system=SystemCode(match.group("system")),
            sequence=int(match.group("seq")),
        )

    @classmethod
    def of(cls, area: str, system: str, sequence: int) -> TrapTag:
        return cls(AreaCode.parse(area), SystemCode.parse(system), sequence)

    def next_in_sequence(self) -> TrapTag:
        """The tag a new trap on the same system would get."""

        return TrapTag(self.area, self.system, self.sequence + 1)

    def in_same_system_as(self, other: TrapTag) -> bool:
        return self.area == other.area and self.system == other.system

    @property
    def prefix(self) -> str:
        return f"{self.area}-{self.system}"

    def __str__(self) -> str:
        return f"{self.prefix}-{self.sequence:0{SEQUENCE_WIDTH}d}"

    def __repr__(self) -> str:
        return f"TrapTag({str(self)!r})"
