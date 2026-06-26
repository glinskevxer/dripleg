"""What happens when the field tablet sends something nobody expected.

Everything here has come off a real export at some point: a note in a language
the office does not use, a technician's name with an accent in it, a tag typed
with a non breaking space in the middle, a cell padded to two hundred
characters by a spreadsheet, and a file that is one long line with no newline
at the end.

None of these should raise anything but a `ValidationError`, and none of them
should silently produce a different trap.
"""

from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.ingest.reader import read_survey_csv
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

HEADER = "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note"


def a_file(rows: list[str], newline: bool = True) -> str:
    text = "\n".join([HEADER, *rows])
    return text + "\n" if newline else text


def test_a_note_in_another_alphabet_survives() -> None:
    result = read_survey_csv(a_file(["B12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,паровая утечка"]))
    assert result.read == 1
    assert result.observations[0].note == "паровая утечка"


def test_a_technician_name_with_an_accent_survives() -> None:
    result = read_survey_csv(a_file(["B12-MP-1,2025-04-08,J Ó Ceallaigh,pass,,,,,,,,,"]))
    assert result.observations[0].technician == "J Ó Ceallaigh"


def test_a_non_breaking_space_in_a_tag_is_refused_not_guessed() -> None:
    result = read_survey_csv(a_file(["B12 MP-1,2025-04-08,R Ellis,pass,,,,,,,,,"]))
    assert result.read == 0
    assert "not a trap tag" in result.quarantined[0].reason


def test_a_spreadsheet_padded_cell_is_stripped() -> None:
    result = read_survey_csv(a_file(["   B12-MP-1   ,2025-04-08,   R Ellis   ,  pass  ,,,,,,,,,"]))
    assert result.read == 1
    assert str(result.observations[0].tag) == "B12-MP-0001"
    assert result.observations[0].technician == "R Ellis"


def test_a_file_with_no_trailing_newline_reads() -> None:
    result = read_survey_csv(a_file(["B12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,"], newline=False))
    assert result.read == 1


def test_a_note_longer_than_the_limit_is_quarantined_not_truncated() -> None:
    long_note = "x" * 500
    result = read_survey_csv(a_file([f"B12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,{long_note}"]))
    assert result.read == 0
    assert "stops at" in result.quarantined[0].reason


def test_a_note_with_a_comma_in_it_needs_quoting_and_gets_it() -> None:
    result = read_survey_csv(a_file(['B12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,"hissing, steady"']))
    assert result.observations[0].note == "hissing, steady"


def test_a_very_long_technician_name_is_kept() -> None:
    name = "R " + "Ellis " * 30
    observation = Observation(
        tag=TrapTag.parse("B12-MP-1"),
        observed_on=dt.date(2025, 4, 8),
        technician=name,
        reported_condition=TrapCondition.OK,
    )
    assert observation.technician.startswith("R Ellis")


def test_a_tag_with_a_very_long_area_is_refused() -> None:
    with pytest.raises(ValidationError, match="not a trap tag"):
        TrapTag.parse("A" * 40 + "-MP-1")


def test_money_parses_a_thousands_separator_and_refuses_a_currency_symbol() -> None:
    assert Money.parse("$1,234.56").cents == 123456
    with pytest.raises(ValidationError, match="cannot read"):
        Money.parse("€1234.56")


def test_a_pressure_written_with_a_unicode_degree_is_refused_as_a_pressure() -> None:
    with pytest.raises(ValidationError, match="cannot read"):
        Pressure.parse("125 psig°")


def test_a_reading_at_an_absurd_pressure_is_refused_by_the_table() -> None:
    from dripleg.steam.saturated import at_pressure

    with pytest.raises(ValidationError):
        at_pressure(Pressure.from_psig(5000.0))


def test_a_file_of_nothing_but_commas_reads_nothing() -> None:
    result = read_survey_csv(a_file([",,,,,,,,,,,,", ",,,,,,,,,,,,"]))
    assert result.read == 0
    assert result.rejected == 0


def test_a_duplicate_header_column_does_not_crash_the_read() -> None:
    text = HEADER + ",note\nB12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,first,second\n"
    result = read_survey_csv(text)
    assert result.read + result.rejected == 1


def test_a_tag_with_a_leading_zero_is_the_same_tag() -> None:
    result = read_survey_csv(
        a_file(
            [
                "B12-MP-0001,2025-04-08,R Ellis,pass,,,,,,,,,",
                "B12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,",
            ]
        )
    )
    assert result.read == 1
    assert "appears twice" in result.quarantined[0].reason
