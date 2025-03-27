from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.readings import (
    SightGlassView,
    SurveyMethod,
    TemperatureReading,
    UltrasonicReading,
)
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature

TAG = TrapTag.parse("B12-MP-0043")
DAY = dt.date(2025, 4, 8)


def temperatures(upstream: float = 340.0, downstream: float = 210.0) -> TemperatureReading:
    return TemperatureReading(
        upstream=Temperature.from_fahrenheit(upstream),
        downstream=Temperature.from_fahrenheit(downstream),
    )


def an_observation(**overrides: object) -> Observation:
    fields: dict[str, object] = {
        "tag": TAG,
        "observed_on": DAY,
        "technician": "R Ellis",
        "reported_condition": TrapCondition.OK,
    }
    fields.update(overrides)
    return Observation(**fields)  # type: ignore[arg-type]


def test_an_observation_keys_on_the_tag_and_the_day() -> None:
    assert an_observation().key == ("B12-MP-0043", DAY)


def test_the_technician_name_is_squeezed() -> None:
    assert an_observation(technician="  R   Ellis ").technician == "R Ellis"


def test_somebody_has_to_have_taken_it() -> None:
    with pytest.raises(ValidationError, match="who took it"):
        an_observation(technician="   ")


def test_an_observation_with_no_readings_is_a_visual() -> None:
    observation = an_observation()
    assert not observation.has_measurements
    assert observation.methods_used == [SurveyMethod.VISUAL]
    assert not observation.is_two_method


def test_ultrasound_alone_is_one_method() -> None:
    observation = an_observation(
        ultrasonic=UltrasonicReading(decibels=42.0, seconds=30.0, cycles=2)
    )
    assert observation.has_measurements
    assert observation.methods_used == [SurveyMethod.ULTRASONIC]
    assert not observation.is_two_method
    assert observation.cycles_per_minute == pytest.approx(4.0)


def test_sound_and_temperature_together_is_two_method() -> None:
    observation = an_observation(
        ultrasonic=UltrasonicReading(decibels=42.0, seconds=30.0, cycles=2),
        temperature=temperatures(),
    )
    assert observation.is_two_method
    assert observation.methods_used == [
        SurveyMethod.ULTRASONIC,
        SurveyMethod.CONTACT_TEMPERATURE,
    ]


def test_an_infrared_reading_is_named_as_infrared() -> None:
    reading = TemperatureReading(
        upstream=Temperature.from_fahrenheit(340.0),
        downstream=Temperature.from_fahrenheit(210.0),
        method=SurveyMethod.INFRARED,
    )
    assert an_observation(temperature=reading).methods_used == [SurveyMethod.INFRARED]


def test_a_readable_sight_glass_counts_as_a_method() -> None:
    seen = an_observation(sight_glass=SightGlassView.LIVE_STEAM)
    assert seen.methods_used == [SurveyMethod.SIGHT_GLASS]
    unseen = an_observation(sight_glass=SightGlassView.CANNOT_SEE)
    assert unseen.methods_used == [SurveyMethod.VISUAL]
    assert unseen.has_measurements


def test_a_trap_that_was_not_reached_carries_no_readings() -> None:
    with pytest.raises(ValidationError, match="not reached"):
        an_observation(
            reported_condition=TrapCondition.NOT_FOUND,
            ultrasonic=UltrasonicReading(decibels=42.0, seconds=30.0),
        )


def test_a_trap_that_was_not_reached_without_readings_is_fine() -> None:
    observation = an_observation(reported_condition=TrapCondition.INACCESSIBLE)
    assert not observation.has_measurements


def test_a_note_is_squeezed_and_bounded() -> None:
    assert an_observation(note="  behind   the   dryer ").note == "behind the dryer"
    with pytest.raises(ValidationError, match="stops at"):
        an_observation(note="x" * 500)


def test_a_blank_photo_reference_is_refused() -> None:
    with pytest.raises(ValidationError, match="cannot be blank"):
        an_observation(photo_reference="  ")
    assert an_observation(photo_reference="IMG_4411.jpg").photo_reference == "IMG_4411.jpg"


def test_the_measured_pressure_wins_over_the_register() -> None:
    register = Pressure.from_psig(125.0)
    assert an_observation().pressure_or(register) == register
    measured = an_observation(measured_pressure=Pressure.from_psig(96.0))
    assert measured.pressure_or(register).psig == pytest.approx(96.0)


def test_the_reported_condition_is_kept_as_written() -> None:
    observation = an_observation(reported_condition=TrapCondition.LEAKING)
    assert observation.reported_condition is TrapCondition.LEAKING


def test_adding_a_note_leaves_the_rest_alone() -> None:
    original = an_observation(ultrasonic=UltrasonicReading(decibels=42.0, seconds=30.0))
    amended = original.with_note("came back with the meter")
    assert amended.note == "came back with the meter"
    assert amended.ultrasonic == original.ultrasonic
    assert original.note == ""


def test_printing_an_observation() -> None:
    assert str(an_observation(reported_condition=TrapCondition.BLOWING_THROUGH)) == (
        "B12-MP-0043 2025-04-08 blowing through"
    )
