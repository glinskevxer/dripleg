from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.model.calendar import DateRange, ProgrammeYear, add_months, months_between


def test_adding_months_keeps_the_day_where_it_can() -> None:
    assert add_months(dt.date(2025, 1, 15), 6) == dt.date(2025, 7, 15)
    assert add_months(dt.date(2025, 7, 15), -6) == dt.date(2025, 1, 15)


def test_adding_months_clamps_at_a_short_month() -> None:
    assert add_months(dt.date(2025, 1, 31), 1) == dt.date(2025, 2, 28)
    assert add_months(dt.date(2024, 1, 31), 1) == dt.date(2024, 2, 29)
    assert add_months(dt.date(2025, 1, 31), 2) == dt.date(2025, 3, 31)


def test_adding_months_rolls_the_year() -> None:
    assert add_months(dt.date(2025, 11, 10), 4) == dt.date(2026, 3, 10)
    assert add_months(dt.date(2025, 2, 10), -4) == dt.date(2024, 10, 10)


def test_whole_months_between_two_dates() -> None:
    assert months_between(dt.date(2025, 1, 15), dt.date(2025, 7, 15)) == 6
    assert months_between(dt.date(2025, 1, 15), dt.date(2025, 7, 14)) == 5
    assert months_between(dt.date(2025, 1, 15), dt.date(2025, 1, 20)) == 0
    assert months_between(dt.date(2025, 7, 15), dt.date(2025, 1, 15)) == -6


def test_a_range_is_half_open() -> None:
    span = DateRange(dt.date(2025, 1, 1), dt.date(2025, 2, 1))
    assert span.covers(dt.date(2025, 1, 1))
    assert span.covers(dt.date(2025, 1, 31))
    assert not span.covers(dt.date(2025, 2, 1))
    assert span.days == 31
    assert span.last_day == dt.date(2025, 1, 31)


def test_touching_ranges_neither_overlap_nor_leave_a_gap() -> None:
    january = DateRange(dt.date(2025, 1, 1), dt.date(2025, 2, 1))
    february = DateRange(dt.date(2025, 2, 1), dt.date(2025, 3, 1))
    assert not january.overlaps(february)
    assert january.end == february.start


def test_a_range_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValidationError, match="ends after it starts"):
        DateRange(dt.date(2025, 2, 1), dt.date(2025, 1, 1))


def test_an_empty_range_is_legal_but_has_no_last_day() -> None:
    empty = DateRange(dt.date(2025, 1, 1), dt.date(2025, 1, 1))
    assert empty.is_empty
    assert empty.days == 0
    assert not empty.covers(dt.date(2025, 1, 1))
    assert str(empty).endswith("(empty)")
    with pytest.raises(ValidationError, match="no last day"):
        _ = empty.last_day


def test_the_handy_constructors() -> None:
    assert DateRange.of_day(dt.date(2025, 5, 4)).days == 1
    assert DateRange.of_year(2025).last_day == dt.date(2025, 12, 31)
    assert DateRange.of_months(dt.date(2025, 1, 31), 1).end == dt.date(2025, 2, 28)
    with pytest.raises(ValidationError, match="backwards in months"):
        DateRange.of_months(dt.date(2025, 1, 1), -1)


def test_overlap_and_intersection() -> None:
    first = DateRange(dt.date(2025, 1, 1), dt.date(2025, 4, 1))
    second = DateRange(dt.date(2025, 3, 1), dt.date(2025, 6, 1))
    assert first.overlaps(second)
    shared = first.intersection(second)
    assert shared == DateRange(dt.date(2025, 3, 1), dt.date(2025, 4, 1))


def test_ranges_that_do_not_meet_intersect_to_nothing() -> None:
    first = DateRange(dt.date(2025, 1, 1), dt.date(2025, 2, 1))
    second = DateRange(dt.date(2025, 3, 1), dt.date(2025, 4, 1))
    assert first.intersection(second) is None
    assert first.clipped_to(second).is_empty


def test_clipping_holds_a_range_inside_another() -> None:
    year = DateRange.of_year(2025)
    wide = DateRange(dt.date(2024, 6, 1), dt.date(2026, 6, 1))
    assert wide.clipped_to(year) == year


def test_printing_a_range() -> None:
    assert str(DateRange.of_year(2025)) == "2025-01-01 to 2025-12-31"


def test_a_calendar_programme_year_is_just_the_year() -> None:
    year = ProgrammeYear(2025)
    assert year.label == "2025"
    assert year.range == DateRange.of_year(2025)
    assert year.covers(dt.date(2025, 12, 31))
    assert not year.covers(dt.date(2026, 1, 1))


def test_a_fiscal_programme_year_straddles_the_new_year() -> None:
    year = ProgrammeYear(2025, start_month=4)
    assert year.label == "2025/26"
    assert year.range.start == dt.date(2025, 4, 1)
    assert year.range.last_day == dt.date(2026, 3, 31)
    assert year.covers(dt.date(2026, 1, 15))


def test_the_year_a_day_falls_in() -> None:
    assert ProgrammeYear.containing(dt.date(2026, 2, 1), start_month=4).starting_year == 2025
    assert ProgrammeYear.containing(dt.date(2026, 5, 1), start_month=4).starting_year == 2026
    assert ProgrammeYear.containing(dt.date(2026, 5, 1)).starting_year == 2026


def test_stepping_from_one_year_to_the_next() -> None:
    year = ProgrammeYear(2025, start_month=4)
    assert year.next().label == "2026/27"
    assert year.previous().label == "2024/25"
    assert year.next().previous() == year


def test_a_programme_year_refuses_nonsense() -> None:
    with pytest.raises(ValidationError, match="starts in a month"):
        ProgrammeYear(2025, start_month=13)
    with pytest.raises(ValidationError, match="starts in a month"):
        ProgrammeYear.containing(dt.date(2025, 1, 1), start_month=0)
    with pytest.raises(ValidationError, match="plausible year"):
        ProgrammeYear(1400)


def test_programme_years_sort_and_print() -> None:
    years = [ProgrammeYear(2026), ProgrammeYear(2024), ProgrammeYear(2025)]
    assert [str(y) for y in sorted(years)] == ["2024", "2025", "2026"]
