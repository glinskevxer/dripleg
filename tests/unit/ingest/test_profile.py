from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.ingest.profile import (
    OPTIONAL_FIELDS,
    PROFILES,
    REQUIRED_FIELDS,
    MappingProfile,
    profile_for_header,
    profile_named,
)


def a_profile(**overrides: object) -> MappingProfile:
    fields: dict[str, object] = {
        "name": "test",
        "columns": {
            "tag": "tag",
            "observed_on": "date",
            "technician": "by",
            "condition": "condition",
        },
    }
    fields.update(overrides)
    return MappingProfile(**fields)  # type: ignore[arg-type]


def test_every_built_in_profile_maps_the_required_fields() -> None:
    for profile in PROFILES.values():
        assert set(profile.columns) >= REQUIRED_FIELDS
        assert set(profile.columns) <= REQUIRED_FIELDS | OPTIONAL_FIELDS


def test_the_profiles_disagree_about_everything_which_is_the_point() -> None:
    assert PROFILES["ultraprobe"].columns["tag"] == "TrapID"
    assert PROFILES["steamscope"].columns["tag"] == "Asset Number"
    assert PROFILES["fieldbook"].columns["tag"] == "tag"


def test_a_profile_states_its_date_order_rather_than_guessing() -> None:
    assert PROFILES["steamscope"].date_order == "dmy"
    assert PROFILES["ultraprobe"].date_order == "ymd"
    with pytest.raises(ValidationError, match="has to be stated"):
        a_profile(date_order="whatever")


def test_a_profile_states_its_units() -> None:
    assert PROFILES["steamscope"].temperature_unit == "C"
    assert PROFILES["steamscope"].pressure_unit == "barg"
    assert PROFILES["fieldbook"].temperature_unit == "F"
    with pytest.raises(ValidationError, match="exported in F or C"):
        a_profile(temperature_unit="K")


def test_a_profile_needs_a_name_and_the_required_columns() -> None:
    with pytest.raises(ValidationError, match="needs a name"):
        a_profile(name="  ")
    with pytest.raises(ValidationError, match="does not map condition"):
        a_profile(columns={"tag": "tag", "observed_on": "date", "technician": "by"})


def test_a_profile_cannot_map_a_field_this_build_does_not_know() -> None:
    with pytest.raises(ValidationError, match="does not know: colour"):
        a_profile(
            columns={
                "tag": "tag",
                "observed_on": "date",
                "technician": "by",
                "condition": "condition",
                "colour": "colour",
            }
        )


def test_two_fields_cannot_point_at_the_same_column() -> None:
    with pytest.raises(ValidationError, match="same column"):
        a_profile(
            columns={
                "tag": "tag",
                "observed_on": "date",
                "technician": "by",
                "condition": "Date",
            }
        )


def test_a_default_probe_window_is_positive() -> None:
    with pytest.raises(ValidationError, match="probe window is positive"):
        a_profile(probe_seconds_default=0.0)


def test_a_profile_answers_which_columns_it_carries() -> None:
    profile = PROFILES["ultraprobe"]
    assert profile.has("cycles")
    assert not profile.has("sight_glass")
    assert profile.column_for("cycles") == "Cycles"
    assert profile.column_for("sight_glass") is None
    assert profile.required_columns == ["Inspector", "Result", "SurveyDate", "TrapID"]


def test_a_header_matches_when_the_required_columns_are_there() -> None:
    profile = PROFILES["fieldbook"]
    assert profile.matches(["tag", "date", "by", "condition", "db"])
    assert profile.matches(["TAG", " Date ", "BY", "Condition"])
    assert not profile.matches(["tag", "date", "by"])
    assert profile.missing_from(["tag", "date", "by"]) == ["condition"]


def test_looking_a_profile_up_by_name() -> None:
    assert profile_named("Ultraprobe") is PROFILES["ultraprobe"]
    assert profile_named("steam scope") is PROFILES["steamscope"]
    with pytest.raises(ValidationError, match="expected one of: fieldbook"):
        profile_named("nothing")


def test_a_header_picks_the_one_profile_that_fits() -> None:
    header = ["TrapID", "SurveyDate", "Inspector", "Result", "dB"]
    assert profile_for_header(header) is PROFILES["ultraprobe"]


def test_a_header_that_fits_nothing_says_what_each_profile_wanted() -> None:
    with pytest.raises(ValidationError, match="no mapping profile fits"):
        profile_for_header(["a", "b", "c"])


def test_a_header_that_fits_two_profiles_is_refused() -> None:
    header = [
        "TrapID",
        "SurveyDate",
        "Inspector",
        "Result",
        "tag",
        "date",
        "by",
        "condition",
    ]
    with pytest.raises(ValidationError, match="more than one profile"):
        profile_for_header(header)


def test_printing_a_profile() -> None:
    assert str(PROFILES["ultraprobe"]) == "ultraprobe (10 columns, dates ymd)"
