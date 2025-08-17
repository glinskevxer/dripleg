"""A plain text table, because a trap survey report gets printed and pinned up.

There is no table library here on purpose. The output has to be stable enough
to diff between two survey years, narrow enough for a portrait page, and read
correctly in a monospaced terminal and in an email that has lost its font. That
is a smaller problem than a general table renderer and it has a different set
of right answers, mostly around numbers.

Numbers right align, text left aligns, and a column that would overflow is
truncated with an ellipsis rather than wrapped, because a wrapped cell breaks
the one property that makes the report diffable: one row per line.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum

from dripleg.errors import ValidationError

__all__ = ["Align", "Column", "Table"]

MIN_WIDTH = 3
GAP = "  "


class Align(Enum):
    LEFT = "left"
    RIGHT = "right"

    @property
    def is_right(self) -> bool:
        return self is Align.RIGHT


@dataclass(frozen=True)
class Column:
    """One column: its heading, how it aligns and how wide it may get."""

    heading: str
    align: Align = Align.LEFT
    max_width: int | None = None

    def __post_init__(self) -> None:
        if not self.heading.strip():
            raise ValidationError("a column needs a heading", field="heading")
        if self.max_width is not None and self.max_width < MIN_WIDTH:
            raise ValidationError(
                f"a column is at least {MIN_WIDTH} characters wide", field="max_width"
            )

    @classmethod
    def number(cls, heading: str, max_width: int | None = None) -> Column:
        return cls(heading=heading, align=Align.RIGHT, max_width=max_width)

    def fit(self, text: str) -> str:
        if self.max_width is None or len(text) <= self.max_width:
            return text
        return text[: self.max_width - 1] + "…"


class Table:
    """Rows of already formatted strings, laid out under their headings."""

    def __init__(self, columns: Sequence[Column]) -> None:
        if not columns:
            raise ValidationError("a table needs at least one column", field="columns")
        self.columns = list(columns)
        self.rows: list[list[str]] = []

    def add(self, values: Iterable[object]) -> None:
        cells = [str(value) for value in values]
        if len(cells) != len(self.columns):
            raise ValidationError(
                f"this table has {len(self.columns)} columns and the row has {len(cells)}",
                field="row",
            )
        self.rows.append(
            [column.fit(cell) for column, cell in zip(self.columns, cells, strict=False)]
        )

    def extend(self, rows: Iterable[Iterable[object]]) -> None:
        for row in rows:
            self.add(row)

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def is_empty(self) -> bool:
        return not self.rows

    def widths(self) -> list[int]:
        widths = [len(column.heading) for column in self.columns]
        for row in self.rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], len(cell))
        return widths

    def lines(self, *, rule: bool = True) -> list[str]:
        widths = self.widths()
        out = [self._line([c.heading for c in self.columns], widths)]
        if rule:
            out.append(GAP.join("-" * width for width in widths))
        out.extend(self._line(row, widths) for row in self.rows)
        return out

    def _line(self, cells: Sequence[str], widths: Sequence[int]) -> str:
        parts = []
        for column, cell, width in zip(self.columns, cells, widths, strict=False):
            parts.append(cell.rjust(width) if column.align.is_right else cell.ljust(width))
        return GAP.join(parts).rstrip()

    def render(self, *, rule: bool = True) -> str:
        return "\n".join(self.lines(rule=rule))

    def __str__(self) -> str:
        return self.render()
