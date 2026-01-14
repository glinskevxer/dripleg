from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.errors import ValidationError
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.programme.calibration import (
    MIN_READINGS,
    CalibrationReport,
    TechnicianRecord,
    calibrate,
)
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from tests.support.build import DAY, a_station, pipe, probe

BLOWING: dict[str, object] = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY: dict[str, object] = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}
ONE_METHOD: dict[str, object] = {"ultrasonic": probe(32.0, 2)}


def a_report(
    rows: list[tuple[str, str, TrapCondition, dict[str, object]]],
) -> CalibrationReport:
    register = TrapRegister([a_station(tag=TrapTag.parse(tag)) for tag, _, _, _ in rows])
    survey = Survey("WRX1", "S2025-1", "Spring", "Vane", DAY - dt.timedelta(days=1))
    for tag, technician, reported, readings in rows:
        survey.record(
            Observation(
                tag=TrapTag.parse(tag),
                observed_on=DAY,
                technician=technician,
                reported_condition=reported,
                **readings,  # type: ignore[arg-type]
            )
        )
    return calibrate(survey, diagnose_survey(register, survey))


def test_a_technician_who_agrees_with_the_rules() -> None:
    report = a_report(
        [
            ("B12-MP-1", "R Ellis", TrapCondition.BLOWING_THROUGH, BLOWING),
            ("B12-MP-2", "R Ellis", TrapCondition.OK, HEALTHY),
        ]
    )
    record = report.records[0]
    assert record.technician == "R Ellis"
    assert record.read == 2
    assert record.agreed == 2
    assert record.agreement_rate == pytest.approx(1.0)
    assert record.leans == "even"


def test_over_calling_is_writing_failure_on_a_passing_trap() -> None:
    report = a_report([("B12-MP-1", "R Ellis", TrapCondition.LEAKING, HEALTHY)])
    record = report.records[0]
    assert record.over_called == 1
    assert record.under_called == 0
    assert record.leans == "over"


def test_under_calling_is_writing_pass_on_a_failing_trap() -> None:
    report = a_report([("B12-MP-1", "R Ellis", TrapCondition.OK, BLOWING)])
    record = report.records[0]
    assert record.under_called == 1
    assert record.over_called == 0
    assert record.leans == "under"


def test_the_two_method_share_is_counted() -> None:
    report = a_report(
        [
            ("B12-MP-1", "R Ellis", TrapCondition.OK, HEALTHY),
            ("B12-MP-2", "R Ellis", TrapCondition.OK, ONE_METHOD),
        ]
    )
    assert report.records[0].two_method == 1
    assert report.records[0].two_method_rate == pytest.approx(0.5)


def test_traps_that_were_not_reached_are_counted() -> None:
    report = a_report(
        [
            ("B12-MP-1", "R Ellis", TrapCondition.NOT_FOUND, {}),
            ("B12-MP-2", "R Ellis", TrapCondition.OK, HEALTHY),
        ]
    )
    assert report.records[0].not_reached == 1
    assert report.records[0].not_reached_rate == pytest.approx(0.5)


def test_two_technicians_are_kept_apart() -> None:
    report = a_report(
        [
            ("B12-MP-1", "R Ellis", TrapCondition.OK, HEALTHY),
            ("B12-MP-2", "J Pike", TrapCondition.OK, BLOWING),
        ]
    )
    assert report.technicians == 2
    assert report.read == 2
    assert report.records[0].technician == "J Pike"


def test_a_small_sample_is_not_rated() -> None:
    report = a_report([("B12-MP-1", "R Ellis", TrapCondition.OK, HEALTHY)])
    assert not report.records[0].is_reportable
    assert report.reportable() == []
    assert report.worst_agreement is None
    assert report.spread == 0.0


def test_a_big_enough_sample_is_rated() -> None:
    rows = [
        (f"B12-MP-{n}", "R Ellis", TrapCondition.OK, HEALTHY) for n in range(1, MIN_READINGS + 1)
    ]
    report = a_report(rows)
    assert report.records[0].is_reportable
    assert report.worst_agreement is not None


def test_the_spread_is_between_the_rated_technicians() -> None:
    rows: list[tuple[str, str, TrapCondition, dict[str, object]]] = []
    for n in range(1, MIN_READINGS + 1):
        rows.append((f"B12-MP-{n}", "R Ellis", TrapCondition.OK, HEALTHY))
    for n in range(1, MIN_READINGS + 1):
        rows.append((f"B12-LP-{n}", "J Pike", TrapCondition.OK, BLOWING))
    report = a_report(rows)
    assert report.spread == pytest.approx(1.0)
    worst = report.worst_agreement
    assert worst is not None
    assert worst.technician == "J Pike"
    assert [r.technician for r in report.leaning("under")] == ["J Pike"]


def test_leaning_takes_a_direction_it_knows() -> None:
    report = a_report([("B12-MP-1", "R Ellis", TrapCondition.OK, HEALTHY)])
    assert report.leaning("sideways") == []


def test_a_record_checks_its_own_arithmetic() -> None:
    with pytest.raises(ValidationError, match="more outcomes than readings"):
        TechnicianRecord(
            "R Ellis", read=1, agreed=1, over_called=1, under_called=0, not_reached=0, two_method=0
        )
    with pytest.raises(ValidationError, match="not negative"):
        TechnicianRecord(
            "R Ellis", read=-1, agreed=0, over_called=0, under_called=0, not_reached=0, two_method=0
        )


def test_an_empty_record_has_no_rates() -> None:
    record = TechnicianRecord("nobody", 0, 0, 0, 0, 0, 0)
    assert record.agreement_rate == 0.0
    assert record.two_method_rate == 0.0
    assert record.not_reached_rate == 0.0


def test_printing_a_record_and_a_report() -> None:
    small = a_report([("B12-MP-1", "R Ellis", TrapCondition.OK, HEALTHY)])
    assert str(small.records[0]) == "R Ellis: 1 readings, too few to rate"
    assert str(small) == "S2025-1: 1 technicians, 1 readings"
