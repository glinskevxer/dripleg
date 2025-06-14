from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.diagnosis.engine import DEFAULT_RULES, DiagnosisEngine
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from tests.unit.diagnosis.conftest import DAY, a_station, pipe, probe


def station(tag: str, **overrides: object):  # type: ignore[no-untyped-def]
    return a_station(tag=TrapTag.parse(tag), **overrides)


def reading(tag: str, condition: TrapCondition, **fields: object) -> Observation:
    return Observation(
        tag=TrapTag.parse(tag),
        observed_on=DAY,
        technician="R Ellis",
        reported_condition=condition,
        **fields,  # type: ignore[arg-type]
    )


def a_survey(readings: list[Observation]) -> Survey:
    survey = Survey("WRX1", "S2025-1", "Spring", "Vane Energy", DAY - dt.timedelta(days=1))
    for item in readings:
        survey.record(item)
    return survey


def test_every_reading_with_a_station_gets_a_verdict() -> None:
    register = TrapRegister([station("B12-MP-1"), station("B12-MP-2")])
    survey = a_survey(
        [
            reading(
                "B12-MP-1",
                TrapCondition.OK,
                ultrasonic=probe(32.0, 2),
                temperature=pipe(350.0, 200.0),
            ),
            reading(
                "B12-MP-2",
                TrapCondition.BLOWING_THROUGH,
                ultrasonic=probe(70.0, 0),
                temperature=pipe(345.0, 258.0),
            ),
        ]
    )
    result = diagnose_survey(register, survey)
    assert len(result) == 2
    assert result.reference == "S2025-1"
    assert result.find("B12-MP-1") is not None
    assert result.find("B12-MP-9") is None


def test_a_reading_on_a_tag_nobody_registered_is_set_aside() -> None:
    register = TrapRegister([station("B12-MP-1")])
    survey = a_survey(
        [reading("B12-MP-1", TrapCondition.OK), reading("B12-MP-9", TrapCondition.LEAKING)]
    )
    result = diagnose_survey(register, survey)
    assert len(result) == 1
    assert [str(t) for t in result.unregistered] == ["B12-MP-0009"]
    assert len(result.skipped) == 1


def test_a_reading_on_a_trap_pulled_before_the_survey_is_set_aside() -> None:
    register = TrapRegister(
        [station("B12-MP-1"), station("B12-MP-2", removed_on=DAY - dt.timedelta(days=30))]
    )
    survey = a_survey(
        [reading("B12-MP-1", TrapCondition.OK), reading("B12-MP-2", TrapCondition.OK)]
    )
    result = diagnose_survey(register, survey)
    assert len(result) == 1
    assert [str(t) for t in result.out_of_service_on_the_day] == ["B12-MP-0002"]


def test_the_counts_come_back_worst_first() -> None:
    register = TrapRegister([station(f"B12-MP-{n}") for n in (1, 2, 3)])
    survey = a_survey(
        [
            reading(
                "B12-MP-1",
                TrapCondition.OK,
                ultrasonic=probe(32.0, 2),
                temperature=pipe(350.0, 200.0),
            ),
            reading(
                "B12-MP-2",
                TrapCondition.OK,
                ultrasonic=probe(70.0, 0),
                temperature=pipe(345.0, 258.0),
            ),
            reading(
                "B12-MP-3",
                TrapCondition.OK,
                ultrasonic=probe(32.0, 2),
                temperature=pipe(350.0, 200.0),
            ),
        ]
    )
    counts = diagnose_survey(register, survey).condition_counts()
    assert list(counts) == [TrapCondition.BLOWING_THROUGH, TrapCondition.OK]
    assert counts[TrapCondition.OK] == 2


def test_the_failure_and_agreement_rates() -> None:
    register = TrapRegister([station(f"B12-MP-{n}") for n in (1, 2)])
    survey = a_survey(
        [
            reading(
                "B12-MP-1",
                TrapCondition.OK,
                ultrasonic=probe(32.0, 2),
                temperature=pipe(350.0, 200.0),
            ),
            reading(
                "B12-MP-2",
                TrapCondition.OK,
                ultrasonic=probe(70.0, 0),
                temperature=pipe(345.0, 258.0),
            ),
        ]
    )
    result = diagnose_survey(register, survey)
    assert result.failure_rate == pytest.approx(0.5)
    assert result.agreement_rate == pytest.approx(0.5)
    assert len(result.disagreements()) == 1
    assert len(result.wasting_steam()) == 1


def test_an_empty_survey_has_no_rates() -> None:
    result = diagnose_survey(TrapRegister(), a_survey([]))
    assert result.failure_rate == 0.0
    assert result.agreement_rate == 0.0
    assert result.condition_counts() == {}
    assert result.worst_first() == []


def test_a_survey_of_unfound_traps_has_no_failure_rate() -> None:
    register = TrapRegister([station("B12-MP-1")])
    survey = a_survey([reading("B12-MP-1", TrapCondition.NOT_FOUND)])
    result = diagnose_survey(register, survey)
    assert result.failure_rate == 0.0
    assert result.agreement_rate == pytest.approx(1.0)


def test_provisional_verdicts_are_collected() -> None:
    register = TrapRegister([station("B12-MP-1")])
    survey = a_survey([reading("B12-MP-1", TrapCondition.OK, ultrasonic=probe(32.0, 2))])
    result = diagnose_survey(register, survey)
    assert len(result.provisional()) == 1


def test_the_worst_first_order() -> None:
    register = TrapRegister([station(f"B12-MP-{n}") for n in (1, 2, 3)])
    survey = a_survey(
        [
            reading(
                "B12-MP-1",
                TrapCondition.OK,
                ultrasonic=probe(32.0, 2),
                temperature=pipe(350.0, 200.0),
            ),
            reading(
                "B12-MP-2",
                TrapCondition.OK,
                ultrasonic=probe(70.0, 0),
                temperature=pipe(345.0, 258.0),
            ),
            reading(
                "B12-MP-3", TrapCondition.OK, ultrasonic=probe(4.0), temperature=pipe(160.0, 130.0)
            ),
        ]
    )
    order = [r.condition for r in diagnose_survey(register, survey).worst_first()]
    assert order[0] is TrapCondition.BLOWING_THROUGH
    assert order[1] is TrapCondition.FAILED_CLOSED
    assert order[-1] is TrapCondition.OK


def test_a_trimmed_engine_is_used_when_given() -> None:
    register = TrapRegister([station("B12-MP-1")])
    survey = a_survey(
        [
            reading(
                "B12-MP-1",
                TrapCondition.OK,
                ultrasonic=probe(70.0, 0),
                temperature=pipe(345.0, 258.0),
            )
        ]
    )
    engine = DiagnosisEngine(DEFAULT_RULES.without("COR-1", "SND-1", "SND-5"))
    result = diagnose_survey(register, survey, engine)
    found = result.find("B12-MP-1")
    assert found is not None
    assert "COR-1" not in found.evidence.rules_fired


def test_printing_a_survey_diagnosis() -> None:
    register = TrapRegister([station("B12-MP-1")])
    survey = a_survey(
        [
            reading(
                "B12-MP-1",
                TrapCondition.OK,
                ultrasonic=probe(70.0, 0),
                temperature=pipe(345.0, 258.0),
            ),
            reading("B12-MP-9", TrapCondition.OK),
        ]
    )
    assert str(diagnose_survey(register, survey)) == ("S2025-1: 1 judged, 1 failures, 1 skipped")
