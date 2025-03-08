"""Turning the short strings in the book back into the enums the model uses.

Every repository was about to grow its own four line loop over an enum, and
the fourth copy is where the error message stops matching. One function, one
message shape, and the field name comes from the enum so a new enum costs
nothing.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import TypeVar

from dripleg.errors import ValidationError

__all__ = ["enum_from_value", "months_from_text", "months_to_text"]

E = TypeVar("E", bound=Enum)

_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")


def _readable(kind: type[Enum]) -> str:
    """`OperatingPrinciple` reads back as `an operating principle`."""

    words = _CAMEL.sub(" ", kind.__name__).lower()
    article = "an" if words[0] in "aeiou" else "a"
    return f"{article} {words}"


def enum_from_value(kind: type[E], text: str, *, field: str | None = None) -> E:
    """Look a stored code up in an enum, or say what was expected."""

    wanted = text.strip().lower()
    for member in kind:
        if str(member.value).lower() == wanted:
            return member
    allowed = ", ".join(sorted(str(m.value) for m in kind))
    raise ValidationError(
        f"{text!r} is not {_readable(kind)}, expected one of: {allowed}",
        field=field or kind.__name__.lower(),
    )


def months_to_text(months: frozenset[int]) -> str:
    """A campaign's months, as the comma list the schema check looks at."""

    return ",".join(str(m) for m in sorted(months))


def months_from_text(text: str) -> frozenset[int]:
    cleaned = text.strip()
    if not cleaned:
        return frozenset()
    months: set[int] = set()
    for part in cleaned.split(","):
        piece = part.strip()
        if not piece.isdigit():
            raise ValidationError(f"{part!r} is not a month number", field="campaign_months")
        months.add(int(piece))
    return frozenset(months)
