from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.survey.readings import (
    SightGlassView,
    SurveyMethod,
    TemperatureReading,
    UltrasonicReading,
)
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature


def test_a_probe_reports_a_cycle_rate_per_minute() -> None:
    reading = UltrasonicReading(decibels=42.0, seconds=30.0, cycles=2)
    assert reading.cycles_per_minute == pytest.approx(4.0)
    assert reading.counted_cycles


def test_a_probe_with_no_count_gives_no_rate() -> None:
    reading = UltrasonicReading(decibels=42.0, seconds=30.0)
    assert reading.cycles_per_minute is None
    assert not reading.counted_cycles
    assert str(reading) == "42 dB"


def test_zero_cycles_with_noise_is_a_continuous_flow() -> None:
    assert UltrasonicReading(decibels=55.0, seconds=30.0, cycles=0).sounded_continuous


def test_zero_cycles_with_no_noise_is_just_quiet() -> None:
    reading = UltrasonicReading(decibels=2.0, seconds=30.0, cycles=0)
    assert reading.is_silent
    assert not reading.sounded_continuous


def test_a_reading_off_the_scale_is_refused() -> None:
    with pytest.raises(ValidationError, match="not a reading off this meter"):
        UltrasonicReading(decibels=180.0, seconds=30.0)
    with pytest.raises(ValidationError, match="not a reading off this meter"):
        UltrasonicReading(decibels=-1.0, seconds=30.0)


def test_a_probe_held_for_a_moment_is_refused() -> None:
    with pytest.raises(ValidationError, match="too short to count a cycle"):
        UltrasonicReading(decibels=42.0, seconds=2.0, cycles=1)


def test_a_negative_cycle_count_and_a_bad_frequency() -> None:
    with pytest.raises(ValidationError, match="not negative"):
        UltrasonicReading(decibels=42.0, seconds=30.0, cycles=-1)
    with pytest.raises(ValidationError, match="has a frequency"):
        UltrasonicReading(decibels=42.0, seconds=30.0, frequency_khz=0.0)


def test_comparing_two_probes() -> None:
    loud = UltrasonicReading(decibels=62.0, seconds=30.0)
    quiet = UltrasonicReading(decibels=18.0, seconds=30.0)
    assert loud.louder_than(quiet)
    assert not quiet.louder_than(loud)


def test_printing_a_probe_with_a_rate() -> None:
    assert str(UltrasonicReading(decibels=42.0, seconds=60.0, cycles=3)) == "42 dB at 3.0/min"


def test_the_methods_know_what_they_measure() -> None:
    assert SurveyMethod.ULTRASONIC.measures_sound
    assert SurveyMethod.ACOUSTIC_STETHOSCOPE.measures_sound
    assert SurveyMethod.INFRARED.measures_temperature
    assert not SurveyMethod.INFRARED.measures_sound
    assert not SurveyMethod.VISUAL.is_quantitative
    assert SurveyMethod.SIGHT_GLASS.is_quantitative


def test_the_sight_glass_views() -> None:
    assert SightGlassView.LIVE_STEAM.suggests_blow_through
    assert not SightGlassView.FLASH.suggests_blow_through
    assert SightGlassView.EMPTY.is_readable
    assert not SightGlassView.CANNOT_SEE.is_readable


def test_the_differential_is_upstream_minus_downstream() -> None:
    reading = TemperatureReading(
        upstream=Temperature.from_fahrenheit(340.0),
        downstream=Temperature.from_fahrenheit(210.0),
    )
    assert reading.differential.fahrenheit == pytest.approx(130.0)
    assert not reading.downstream_is_hot


def test_a_small_drop_across_the_trap_reads_as_hot() -> None:
    reading = TemperatureReading(
        upstream=Temperature.from_fahrenheit(340.0),
        downstream=Temperature.from_fahrenheit(332.0),
    )
    assert reading.downstream_is_hot
    assert reading.differential.fahrenheit == pytest.approx(8.0)


def test_subcooling_is_measured_against_the_header() -> None:
    reading = TemperatureReading(
        upstream=Temperature.from_fahrenheit(340.0),
        downstream=Temperature.from_fahrenheit(210.0),
    )
    gap = reading.subcooling_below(Pressure.from_psig(125.0))
    assert gap.fahrenheit == pytest.approx(13.0, abs=1.5)


def test_a_cold_trap_is_a_long_way_under_saturation() -> None:
    cold = TemperatureReading(
        upstream=Temperature.from_fahrenheit(150.0),
        downstream=Temperature.from_fahrenheit(120.0),
    )
    assert cold.is_cold(Pressure.from_psig(125.0))
    warm = TemperatureReading(
        upstream=Temperature.from_fahrenheit(345.0),
        downstream=Temperature.from_fahrenheit(220.0),
    )
    assert not warm.is_cold(Pressure.from_psig(125.0))


def test_the_rise_above_ambient_where_there_is_one() -> None:
    reading = TemperatureReading(
        upstream=Temperature.from_fahrenheit(340.0),
        downstream=Temperature.from_fahrenheit(210.0),
        ambient=Temperature.from_fahrenheit(72.0),
    )
    assert reading.rise_above_ambient() is not None
    assert reading.rise_above_ambient().fahrenheit == pytest.approx(138.0)  # type: ignore[union-attr]


def test_no_ambient_means_no_rise() -> None:
    reading = TemperatureReading(
        upstream=Temperature.from_fahrenheit(340.0),
        downstream=Temperature.from_fahrenheit(210.0),
    )
    assert reading.rise_above_ambient() is None


def test_the_air_cannot_be_hotter_than_the_inlet() -> None:
    with pytest.raises(ValidationError, match="hotter than the pipe"):
        TemperatureReading(
            upstream=Temperature.from_fahrenheit(120.0),
            downstream=Temperature.from_fahrenheit(110.0),
            ambient=Temperature.from_fahrenheit(200.0),
        )


def test_a_temperature_reading_needs_a_temperature_method() -> None:
    with pytest.raises(ValidationError, match="does not measure a temperature"):
        TemperatureReading(
            upstream=Temperature.from_fahrenheit(340.0),
            downstream=Temperature.from_fahrenheit(210.0),
            method=SurveyMethod.ULTRASONIC,
        )


def test_an_infrared_reading_is_allowed() -> None:
    reading = TemperatureReading(
        upstream=Temperature.from_fahrenheit(340.0),
        downstream=Temperature.from_fahrenheit(210.0),
        method=SurveyMethod.INFRARED,
    )
    assert reading.method is SurveyMethod.INFRARED
    assert str(reading) == "340.0 F / 210.0 F"
