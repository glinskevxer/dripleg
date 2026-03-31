from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import DriplegError, ValidationError
from dripleg.ingest.profile import PROFILES
from dripleg.ingest.reader import read_survey_csv
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SightGlassView

FIELDBOOK = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-43,2025-04-08,R Ellis,blowing through,68,30,0,345,258,74,live_steam,118,plume\n"
    "B12-MP-44,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,\n"
)

STEAMSCOPE = (
    "Asset Number,Date,Tech,Status,Ultrasound,Inlet C,Outlet C,Ambient C,Line bar,Note,Photo\n"
    "B12-MP-43,08/04/2025,J Pike,failed open,68,174,126,23,8.6,plume,IMG_1.jpg\n"
)


def test_a_fieldbook_export_reads() -> None:
    result = read_survey_csv(FIELDBOOK)
    assert result.profile is PROFILES["fieldbook"]
    assert result.read == 2
    assert result.is_clean
    assert result.acceptance_rate == 1.0


def test_every_field_comes_through() -> None:
    first = read_survey_csv(FIELDBOOK).observations[0]
    assert str(first.tag) == "B12-MP-0043"
    assert first.observed_on == dt.date(2025, 4, 8)
    assert first.technician == "R Ellis"
    assert first.reported_condition is TrapCondition.BLOWING_THROUGH
    assert first.ultrasonic is not None
    assert first.ultrasonic.decibels == pytest.approx(68.0)
    assert first.ultrasonic.cycles == 0
    assert first.temperature is not None
    assert first.temperature.upstream.fahrenheit == pytest.approx(345.0)
    assert first.sight_glass is SightGlassView.LIVE_STEAM
    assert first.measured_pressure is not None
    assert first.measured_pressure.psig == pytest.approx(118.0)
    assert first.note == "plume"


def test_blank_optional_columns_come_through_as_nothing() -> None:
    second = read_survey_csv(FIELDBOOK).observations[1]
    assert second.sight_glass is None
    assert second.measured_pressure is None
    assert second.photo_reference is None
    assert second.temperature is not None
    assert second.temperature.ambient is None


def test_a_steamscope_export_converts_its_units() -> None:
    result = read_survey_csv(STEAMSCOPE)
    assert result.profile is PROFILES["steamscope"]
    observation = result.observations[0]
    assert observation.observed_on == dt.date(2025, 4, 8)
    assert observation.temperature is not None
    assert observation.temperature.upstream.fahrenheit == pytest.approx(345.2, abs=0.1)
    assert observation.measured_pressure is not None
    assert observation.measured_pressure.psig == pytest.approx(124.7, abs=0.5)
    assert observation.reported_condition is TrapCondition.BLOWING_THROUGH
    assert observation.photo_reference == "IMG_1.jpg"


def test_the_probe_window_falls_back_to_the_profile_default() -> None:
    observation = read_survey_csv(STEAMSCOPE).observations[0]
    assert observation.ultrasonic is not None
    assert observation.ultrasonic.seconds == pytest.approx(30.0)
    assert observation.ultrasonic.cycles is None


def test_the_date_order_is_taken_from_the_profile() -> None:
    # 08/04/2025 is the eighth of April under a dmy profile.
    assert read_survey_csv(STEAMSCOPE).observations[0].observed_on == dt.date(2025, 4, 8)


def test_a_date_in_the_wrong_order_is_quarantined() -> None:
    text = STEAMSCOPE.replace("08/04/2025", "2025-04-08")
    result = read_survey_csv(text)
    assert result.read == 0
    assert result.rejected == 1
    assert "is not a dmy date" in result.quarantined[0].reason


def test_a_bad_tag_loses_its_row_and_nothing_else() -> None:
    text = FIELDBOOK.replace("B12-MP-44", "not a tag")
    result = read_survey_csv(text)
    assert result.read == 1
    assert result.rejected == 1
    assert result.quarantined[0].line == 3
    assert "not a trap tag" in result.quarantined[0].reason
    assert result.quarantined[0].values["by"] == "R Ellis"


def test_a_condition_nobody_writes_is_quarantined() -> None:
    text = FIELDBOOK.replace("blowing through", "looked odd")
    result = read_survey_csv(text)
    assert result.rejected == 1
    assert "not a trap condition" in result.quarantined[0].reason


def test_a_number_that_is_not_a_number_is_quarantined() -> None:
    text = FIELDBOOK.replace(",68,30,0,", ",loud,30,0,")
    result = read_survey_csv(text)
    assert result.rejected == 1
    assert "is not a number" in result.quarantined[0].reason


def test_one_side_of_a_temperature_pair_is_quarantined() -> None:
    text = FIELDBOOK.replace(",345,258,74,", ",345,,74,")
    result = read_survey_csv(text)
    assert result.rejected == 1
    assert "only one side" in result.quarantined[0].reason


def test_a_row_with_no_date_is_quarantined() -> None:
    text = FIELDBOOK.replace("2025-04-08,R Ellis,blowing", ",R Ellis,blowing")
    result = read_survey_csv(text)
    assert result.rejected == 1
    assert "no date on it" in result.quarantined[0].reason


def test_a_bad_sight_glass_reading_is_quarantined() -> None:
    text = FIELDBOOK.replace("live_steam", "purple")
    result = read_survey_csv(text)
    assert result.rejected == 1
    assert "not a sight glass reading" in result.quarantined[0].reason


def test_a_tag_twice_in_one_file_keeps_the_first() -> None:
    text = FIELDBOOK + ("B12-MP-43,2025-04-09,R Ellis,pass,20,30,,,,,,,\n")
    result = read_survey_csv(text)
    assert result.read == 2
    assert result.rejected == 1
    assert "appears twice" in result.quarantined[0].reason
    assert result.observations[0].reported_condition is TrapCondition.BLOWING_THROUGH


def test_a_named_profile_can_be_forced() -> None:
    result = read_survey_csv(FIELDBOOK, PROFILES["fieldbook"])
    assert result.read == 2


def test_a_forced_profile_that_does_not_fit_is_refused() -> None:
    with pytest.raises(ValidationError, match="needs columns this file does not have"):
        read_survey_csv(FIELDBOOK, PROFILES["ultraprobe"])


def test_a_file_with_no_header_is_refused() -> None:
    with pytest.raises(DriplegError, match="no header row"):
        read_survey_csv("")


def test_a_file_nothing_recognises_is_refused() -> None:
    with pytest.raises(ValidationError, match="no mapping profile fits"):
        read_survey_csv("a,b,c\n1,2,3\n")


def test_the_content_hash_follows_the_bytes() -> None:
    first = read_survey_csv(FIELDBOOK)
    same = read_survey_csv(FIELDBOOK)
    different = read_survey_csv(FIELDBOOK.replace("R Ellis", "J Pike"))
    assert first.content_hash == same.content_hash
    assert first.content_hash != different.content_hash
    assert len(first.content_hash) == 64


def test_a_header_only_file_reads_nothing() -> None:
    result = read_survey_csv("tag,date,by,condition\n")
    assert result.total_rows == 0
    assert result.acceptance_rate == 0.0
    assert result.is_clean


def test_printing_a_result_and_a_quarantined_row() -> None:
    result = read_survey_csv(FIELDBOOK.replace("B12-MP-44", "rubbish"))
    assert str(result).startswith("fieldbook: 1 read, 1 quarantined (")
    assert str(result.quarantined[0]).startswith("line 3: ")


def test_a_byte_order_mark_does_not_stop_the_file_reading() -> None:
    result = read_survey_csv("﻿" + FIELDBOOK)
    assert result.read == 2
    assert result.is_clean


def test_a_byte_order_mark_does_not_change_the_hash() -> None:
    assert read_survey_csv("﻿" + FIELDBOOK).content_hash == read_survey_csv(FIELDBOOK).content_hash


def test_a_semicolon_export_reads() -> None:
    result = read_survey_csv(FIELDBOOK.replace(",", ";"))
    assert result.read == 2
    assert result.observations[0].technician == "R Ellis"


def test_a_tab_export_reads() -> None:
    result = read_survey_csv(FIELDBOOK.replace(",", "\t"))
    assert result.read == 2


def test_the_delimiter_is_decided_on_the_header_alone() -> None:
    from dripleg.ingest.reader import sniff_dialect

    assert sniff_dialect(FIELDBOOK) == ","
    assert sniff_dialect(FIELDBOOK.replace(",", ";")) == ";"
    assert sniff_dialect("") == ","
    assert sniff_dialect("tag\n") == ","


def test_a_note_full_of_semicolons_does_not_change_the_delimiter() -> None:
    text = FIELDBOOK.replace("plume", "hissing; steady; loud")
    assert read_survey_csv(text).read == 2


def test_trailing_blank_lines_are_ignored() -> None:
    result = read_survey_csv(FIELDBOOK + "\n\n,,,,,,,,,,,,\n")
    assert result.read == 2
    assert result.is_clean


def test_a_blank_line_in_the_middle_is_ignored() -> None:
    first, rest = FIELDBOOK.split("\n", 1)
    result = read_survey_csv(f"{first}\n\n{rest}")
    assert result.read == 2
    assert result.is_clean
