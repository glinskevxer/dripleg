from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.report.table import Align, Column, Table


def a_table() -> Table:
    table = Table([Column("tag"), Column.number("lb/h"), Column("condition")])
    table.add(["B12-MP-0043", "48.2", "blowing through"])
    table.add(["B12-MP-0044", "0.0", "ok"])
    return table


def test_a_column_needs_a_heading() -> None:
    with pytest.raises(ValidationError, match="needs a heading"):
        Column("  ")


def test_a_column_has_a_sensible_minimum_width() -> None:
    with pytest.raises(ValidationError, match="at least 3 characters"):
        Column("tag", max_width=1)


def test_a_number_column_aligns_right() -> None:
    assert Column.number("lb/h").align is Align.RIGHT
    assert Column("tag").align is Align.LEFT
    assert Align.RIGHT.is_right
    assert not Align.LEFT.is_right


def test_a_long_cell_is_truncated_rather_than_wrapped() -> None:
    column = Column("note", max_width=8)
    assert column.fit("short") == "short"
    assert column.fit("a very long note indeed") == "a very …"
    assert len(column.fit("a very long note indeed")) == 8


def test_a_table_needs_a_column() -> None:
    with pytest.raises(ValidationError, match="at least one column"):
        Table([])


def test_a_row_has_to_be_the_right_width() -> None:
    table = Table([Column("tag"), Column("condition")])
    with pytest.raises(ValidationError, match="2 columns and the row has 3"):
        table.add(["a", "b", "c"])


def test_an_empty_table_still_prints_its_heading() -> None:
    table = Table([Column("tag"), Column("condition")])
    assert table.is_empty
    lines = table.lines()
    assert lines[0].startswith("tag")
    assert set(lines[1]) <= {"-", " "}
    assert len(lines) == 2


def test_the_columns_are_as_wide_as_their_widest_cell() -> None:
    table = a_table()
    assert table.widths() == [11, 4, 15]


def test_numbers_line_up_on_the_right() -> None:
    lines = a_table().lines()
    first = lines[2]
    second = lines[3]
    assert "48.2" in first
    assert first.index("48.2") + 4 == second.index("0.0") + 3


def test_text_lines_up_on_the_left() -> None:
    lines = a_table().lines()
    assert lines[2].startswith("B12-MP-0043")
    assert lines[3].startswith("B12-MP-0044")


def test_the_rule_can_be_left_off() -> None:
    with_rule = a_table().lines()
    without = a_table().lines(rule=False)
    assert len(with_rule) == len(without) + 1
    assert without[1].startswith("B12-MP-0043")


def test_trailing_space_is_stripped() -> None:
    for line in a_table().lines():
        assert line == line.rstrip()


def test_rows_can_be_added_in_bulk() -> None:
    table = Table([Column("a"), Column("b")])
    table.extend([["1", "2"], ["3", "4"]])
    assert len(table) == 2


def test_values_do_not_have_to_be_strings() -> None:
    table = Table([Column("a"), Column.number("b")])
    table.add(["x", 42])
    assert "42" in table.render()


def test_rendering_joins_the_lines() -> None:
    table = a_table()
    assert table.render() == "\n".join(table.lines())
    assert str(table) == table.render()


def test_one_row_per_line_survives_a_long_cell() -> None:
    table = Table([Column("tag"), Column("note", max_width=10)])
    table.add(["B12-MP-1", "a note that is far too long for the column"])
    assert len(table.lines()) == 3
