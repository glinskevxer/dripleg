"""What every report in this package has in common, which is not very much.

Three things, and they were copied into five classes before this existed:
turning the lines into one string, writing them to a stream, and holding the
text and the json shape to each other so a report cannot grow a field in one
and not the other.

The last one is the only interesting one. A report that prints a number the
json does not carry is a report somebody will re-derive by hand from the text,
badly, and a report whose json carries a number the text does not print is a
number nobody has ever read. So `check_shape` is a test helper that holds both
against a list of keys, and every report's tests call it.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Protocol, TextIO, runtime_checkable

__all__ = [
    "Rendered",
    "Report",
]


@runtime_checkable
class Report(Protocol):
    """Anything this package can print as text or hand over as json."""

    @abstractmethod
    def lines(self) -> list[str]:
        """The report as a person reads it, one line at a time."""

    @abstractmethod
    def as_dict(self) -> dict[str, object]:
        """The same report as whatever reads it next."""


class Rendered:
    """The two things every report does with its lines.

    A mixin rather than a base class, because the reports are frozen
    dataclasses and putting a dataclass under a base class that is not one
    causes more trouble than the two methods are worth.
    """

    def lines(self) -> list[str]:  # pragma: no cover - every report overrides this
        raise NotImplementedError

    def render(self) -> str:
        return "\n".join(self.lines())

    def write_to(self, stream: TextIO) -> int:
        """Write the report out and say how many lines went."""

        written = self.lines()
        for line in written:
            stream.write(line + "\n")
        return len(written)

    def __str__(self) -> str:
        return self.render()
