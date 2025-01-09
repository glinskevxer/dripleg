"""The exceptions this package raises, and nothing else.

Everything here descends from :class:`DriplegError`, so a caller that wants to
catch anything the library considers its own fault can catch that one name.
Anything else escaping the library is a bug in the library.
"""

from __future__ import annotations

__all__ = [
    "ConfigError",
    "ConflictError",
    "DriplegError",
    "NotFoundError",
    "OutOfRangeError",
    "UnitError",
    "ValidationError",
]


class DriplegError(Exception):
    """Base class for every error this package raises deliberately."""


class ValidationError(DriplegError):
    """A value was not acceptable where it was used.

    Carries the field it came from so a bulk importer can quarantine the row
    and say which column failed rather than dropping the whole file.
    """

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field

    def __str__(self) -> str:
        base = super().__str__()
        if self.field is None:
            return base
        return f"{self.field}: {base}"


class UnitError(ValidationError):
    """A quantity was handed a unit it does not know, or the wrong dimension."""


class OutOfRangeError(ValidationError):
    """A value was inside its type but outside the range the caller supports.

    Steam property lookups raise this rather than extrapolating. A table that
    stops at 1000 psia should say so, not hand back a number nobody can defend.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        low: float | None = None,
        high: float | None = None,
        value: float | None = None,
    ) -> None:
        super().__init__(message, field=field)
        self.low = low
        self.high = high
        self.value = value


class NotFoundError(DriplegError):
    """A record was asked for by key and is not there."""

    def __init__(self, kind: str, key: object) -> None:
        super().__init__(f"no {kind} with key {key!r}")
        self.kind = kind
        self.key = key


class ConflictError(DriplegError):
    """A write would break something the store is holding true."""


class ConfigError(DriplegError):
    """The configuration handed to the library does not make sense."""
