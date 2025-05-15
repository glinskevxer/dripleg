from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.errors import ValidationError
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.tags import TrapTag
from dripleg.units.pressure import Pressure
from tests.unit.diagnosis.conftest import a_header, a_model, a_reading, a_station, pipe, probe


def test_the_context_checks_the_reading_belongs_to_the_station() -> None:
    with pytest.raises(ValidationError, match="reading is for"):
        DiagnosisContext(a_station(), a_reading(tag=TrapTag.parse("B12-MP-0044")))


def test_a_reading_taken_after_the_trap_came_out_is_refused() -> None:
    station = a_station(removed_on=dt.date(2025, 1, 1))
    with pytest.raises(ValidationError, match="not in service"):
        DiagnosisContext(station, a_reading())


def test_the_pressure_comes_from_the_register_by_default() -> None:
    context = DiagnosisContext(a_station(), a_reading())
    assert context.pressure.psig == pytest.approx(125.0)
    assert not context.pressure_was_measured


def test_a_measured_pressure_wins() -> None:
    context = DiagnosisContext(a_station(), a_reading(measured_pressure=Pressure.from_psig(96.0)))
    assert context.pressure.psig == pytest.approx(96.0)
    assert context.pressure_was_measured


def test_the_saturation_temperature_follows_the_pressure_used() -> None:
    register = DiagnosisContext(a_station(), a_reading())
    measured = DiagnosisContext(a_station(), a_reading(measured_pressure=Pressure.from_psig(30.0)))
    assert register.saturation_temperature.fahrenheit == pytest.approx(353.0, abs=1.5)
    assert measured.saturation_temperature.fahrenheit == pytest.approx(274.0, abs=2.0)


def test_a_measured_pressure_far_from_the_register_is_flagged() -> None:
    close = DiagnosisContext(a_station(), a_reading(measured_pressure=Pressure.from_psig(115.0)))
    assert not close.pressure_disagrees_with_register
    far = DiagnosisContext(a_station(), a_reading(measured_pressure=Pressure.from_psig(40.0)))
    assert far.pressure_disagrees_with_register


def test_no_measured_pressure_never_disagrees() -> None:
    assert not DiagnosisContext(a_station(), a_reading()).pressure_disagrees_with_register


def test_the_back_pressure_ratio_and_choking() -> None:
    context = DiagnosisContext(a_station(), a_reading())
    assert context.back_pressure_ratio == pytest.approx(29.696 / 139.696, abs=0.001)
    assert context.is_choked
    loaded = DiagnosisContext(
        a_station(header=a_header(operating=30.0, discharge=25.0)), a_reading()
    )
    assert not loaded.is_choked


def test_a_reading_with_nothing_measured_answers_none() -> None:
    context = DiagnosisContext(a_station(), a_reading())
    assert not context.has_sound
    assert not context.has_heat
    assert context.subcooling is None
    assert context.differential is None
    assert context.cycles_per_minute is None
    assert context.subcooling_is_normal is None
    assert context.cycle_rate_is_normal is None


def test_subcooling_is_measured_against_the_pressure_in_use() -> None:
    context = DiagnosisContext(a_station(), a_reading(temperature=pipe(340.0, 210.0)))
    assert context.subcooling is not None
    assert context.subcooling.fahrenheit == pytest.approx(13.0, abs=1.5)
    assert context.differential is not None
    assert context.differential.fahrenheit == pytest.approx(130.0)


def test_a_disc_trap_at_saturation_reads_as_normal_subcooling() -> None:
    context = DiagnosisContext(a_station(), a_reading(temperature=pipe(350.0, 220.0)))
    assert context.subcooling_is_normal


def test_a_disc_trap_running_cold_does_not() -> None:
    context = DiagnosisContext(a_station(), a_reading(temperature=pipe(280.0, 200.0)))
    assert context.subcooling_is_normal is False


def test_a_thermostatic_trap_is_allowed_to_run_cold() -> None:
    station = a_station(model=a_model(OperatingPrinciple.BIMETALLIC))
    context = DiagnosisContext(station, a_reading(temperature=pipe(300.0, 200.0)))
    assert context.subcooling_is_normal


def test_an_inlet_above_saturation_does_not_go_negative() -> None:
    context = DiagnosisContext(a_station(), a_reading(temperature=pipe(380.0, 210.0)))
    assert context.subcooling is not None
    assert context.subcooling.fahrenheit < 0
    assert context.subcooling_is_normal


def test_the_cycle_rate_is_judged_against_the_principle() -> None:
    disc = DiagnosisContext(a_station(), a_reading(ultrasonic=probe(42.0, cycles=2)))
    assert disc.cycle_rate_is_normal
    fast = DiagnosisContext(a_station(), a_reading(ultrasonic=probe(42.0, cycles=8)))
    assert fast.cycle_rate_is_normal is False


def test_the_principle_profile_comes_off_the_model() -> None:
    station = a_station(model=a_model(OperatingPrinciple.FLOAT_THERMOSTATIC))
    context = DiagnosisContext(station, a_reading())
    assert context.principle.principle is OperatingPrinciple.FLOAT_THERMOSTATIC


def test_the_readings_are_handed_through() -> None:
    context = DiagnosisContext(
        a_station(), a_reading(ultrasonic=probe(42.0, cycles=2), temperature=pipe(340.0, 210.0))
    )
    assert context.sound is not None
    assert context.heat is not None
    assert context.observed_on == context.observation.observed_on
    assert context.discharge_pressure.psig == pytest.approx(15.0)


def test_printing_a_context() -> None:
    context = DiagnosisContext(a_station(), a_reading())
    assert str(context) == "B12-MP-0043 on 2025-04-08 at 125.0 psig"
