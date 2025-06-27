from __future__ import annotations

import pytest

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.engine import DEFAULT_RULES, Diagnosis, DiagnosisEngine
from dripleg.model.principles import OperatingPrinciple
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SightGlassView
from dripleg.units.pressure import Pressure
from tests.support.build import a_model, a_reading, a_station, pipe, probe


def diagnose(
    *,
    reported: TrapCondition = TrapCondition.OK,
    principle: OperatingPrinciple = OperatingPrinciple.THERMODYNAMIC_DISC,
    **reading: object,
) -> Diagnosis:
    context = DiagnosisContext(
        a_station(model=a_model(principle)),
        a_reading(reported_condition=reported, **reading),
    )
    return DiagnosisEngine().diagnose(context)


def test_the_default_set_holds_every_rule_family() -> None:
    codes = DEFAULT_RULES.codes
    assert any(c.startswith("SND-") for c in codes)
    assert any(c.startswith("TMP-") for c in codes)
    assert any(c.startswith("VIS-") for c in codes)
    assert any(c.startswith("COR-") for c in codes)
    assert len(set(codes)) == len(codes)


def test_a_trap_that_was_not_found_keeps_the_field_code() -> None:
    result = diagnose(reported=TrapCondition.NOT_FOUND)
    assert result.condition is TrapCondition.NOT_FOUND
    assert result.confidence == 1.0
    assert "not assessed" in result.flags
    assert not result.has_evidence


def test_a_visual_pass_with_no_readings_keeps_the_field_code() -> None:
    result = diagnose(reported=TrapCondition.OK)
    assert result.condition is TrapCondition.OK
    assert result.confidence == 0.0
    assert "no readings taken" in result.flags
    assert result.is_provisional
    assert result.agrees_with_technician


def test_a_clear_blow_through_on_two_methods() -> None:
    result = diagnose(ultrasonic=probe(70.0, 0), temperature=pipe(345.0, 258.0))
    assert result.condition is TrapCondition.BLOWING_THROUGH
    assert result.confidence >= 0.8
    assert not result.is_provisional
    assert "differs from the field code" in result.flags
    assert result.severity_factor == 1.0


def test_a_sight_glass_settles_it_outright() -> None:
    result = diagnose(ultrasonic=probe(20.0), sight_glass=SightGlassView.LIVE_STEAM)
    assert result.condition is TrapCondition.BLOWING_THROUGH
    assert result.confidence == pytest.approx(1.0)


def test_a_dead_line_beats_the_seat_noise() -> None:
    result = diagnose(
        ultrasonic=probe(70.0, 0),
        temperature=pipe(90.0, 85.0, ambient=72.0),
    )
    assert result.condition is TrapCondition.OUT_OF_SERVICE
    assert result.confidence >= 0.4


def test_a_healthy_trap_on_two_methods() -> None:
    result = diagnose(ultrasonic=probe(32.0, 2), temperature=pipe(350.0, 200.0))
    assert result.condition is TrapCondition.OK
    assert result.agrees_with_technician
    assert not result.is_provisional
    assert result.severity_factor == 0.0


def test_one_method_knocks_the_confidence_down() -> None:
    one = diagnose(ultrasonic=probe(32.0, 2))
    two = diagnose(ultrasonic=probe(32.0, 2), temperature=pipe(350.0, 200.0))
    assert one.confidence < two.confidence
    assert "single method" in one.flags
    assert one.is_provisional
    assert "one method only" in one.flags


def test_contested_evidence_knocks_the_confidence_down() -> None:
    result = diagnose(ultrasonic=probe(50.0, None), temperature=pipe(160.0, 130.0))
    assert "contested" in result.flags
    assert result.condition in {TrapCondition.PLUGGED, TrapCondition.FAILED_CLOSED}


def test_a_measured_pressure_a_long_way_off_is_flagged() -> None:
    result = diagnose(
        measured_pressure=Pressure.from_psig(30.0),
        ultrasonic=probe(32.0, 2),
        temperature=pipe(270.0, 180.0),
    )
    assert any("off the register" in flag for flag in result.flags)


def test_a_cold_quiet_trap_reads_as_failed_closed() -> None:
    result = diagnose(ultrasonic=probe(4.0), temperature=pipe(160.0, 130.0))
    assert result.condition is TrapCondition.FAILED_CLOSED
    assert result.confidence >= 0.5


def test_the_verdict_carries_its_reasons() -> None:
    result = diagnose(ultrasonic=probe(70.0, 0), temperature=pipe(345.0, 258.0))
    reasons = result.reasons()
    assert reasons
    assert any(line.startswith("COR-1") for line in reasons)
    assert all("->" in line for line in reasons)


def test_agreement_with_the_technician_is_recorded_either_way() -> None:
    agreed = diagnose(
        reported=TrapCondition.BLOWING_THROUGH,
        ultrasonic=probe(70.0, 0),
        temperature=pipe(345.0, 258.0),
    )
    assert agreed.agrees_with_technician
    assert "differs from the field code" not in agreed.flags


def test_diagnosing_a_list_in_one_go() -> None:
    contexts = [
        DiagnosisContext(a_station(), a_reading(ultrasonic=probe(70.0, 0))),
        DiagnosisContext(a_station(), a_reading(ultrasonic=probe(32.0, 2))),
    ]
    results = DiagnosisEngine().diagnose_all(contexts)
    assert [r.condition for r in results] == [
        TrapCondition.BLOWING_THROUGH,
        TrapCondition.OK,
    ]


def test_an_engine_can_be_given_a_trimmed_rule_set() -> None:
    engine = DiagnosisEngine(DEFAULT_RULES.without("COR-1"))
    context = DiagnosisContext(
        a_station(), a_reading(ultrasonic=probe(70.0, 0), temperature=pipe(345.0, 258.0))
    )
    result = engine.diagnose(context)
    assert "COR-1" not in result.evidence.rules_fired
    assert result.condition is TrapCondition.BLOWING_THROUGH


def test_printing_a_diagnosis() -> None:
    result = diagnose(ultrasonic=probe(20.0), sight_glass=SightGlassView.LIVE_STEAM)
    assert str(result) == "B12-MP-0043 2025-04-08 blowing through (100% confident)"
