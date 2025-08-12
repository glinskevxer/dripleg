from __future__ import annotations

from dataclasses import replace

import pytest

from dripleg.errors import ValidationError
from dripleg.model.attributes import ServiceType
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.programme.reliability import (
    MIN_SAMPLE,
    FailureRate,
    ReliabilityReport,
    build_reliability,
)
from dripleg.survey.condition import TrapCondition
from tests.support.build import a_model, a_station

BLOW = TrapCondition.BLOWING_THROUGH
OK = TrapCondition.OK
LOST = TrapCondition.NOT_FOUND


def a_report(rows: list[tuple[str, list[TrapCondition]]], **station: object) -> ReliabilityReport:
    register = TrapRegister([a_station(tag=TrapTag.parse(tag), **station) for tag, _ in rows])
    history = {TrapTag.parse(tag): verdicts for tag, verdicts in rows}
    return build_reliability(register, history)


def test_a_rate_is_failures_over_assessments() -> None:
    rate = FailureRate("TD52", assessed=10, failed=3)
    assert rate.rate == pytest.approx(0.3)
    assert rate.is_reportable


def test_a_rate_with_no_assessments_is_zero() -> None:
    assert FailureRate("TD52", assessed=0, failed=0).rate == 0.0


def test_a_small_sample_is_not_reportable() -> None:
    assert not FailureRate("TD52", assessed=MIN_SAMPLE - 1, failed=1).is_reportable
    assert FailureRate("TD52", assessed=MIN_SAMPLE, failed=1).is_reportable


def test_a_rate_checks_itself() -> None:
    with pytest.raises(ValidationError, match="more failures than assessments"):
        FailureRate("TD52", assessed=2, failed=3)
    with pytest.raises(ValidationError, match="not negative"):
        FailureRate("TD52", assessed=-1, failed=0)


def test_unassessed_readings_drop_out_of_the_denominator() -> None:
    report = a_report([("B12-MP-1", [OK, LOST, BLOW])])
    rate = report.by_model[0]
    assert rate.assessed == 2
    assert rate.failed == 1


def test_a_trap_with_no_history_is_left_out() -> None:
    report = a_report([("B12-MP-1", []), ("B12-MP-2", [BLOW])])
    assert report.by_model[0].assessed == 1


def test_the_cuts_all_see_the_same_readings() -> None:
    report = a_report([("B12-MP-1", [OK, BLOW])])
    for cut in (report.by_model, report.by_principle, report.by_service, report.by_pressure):
        assert len(cut) == 1
        assert cut[0].assessed == 2
        assert cut[0].failed == 1


def test_the_cuts_are_labelled_the_way_a_report_prints_them() -> None:
    report = a_report([("B12-MP-1", [OK])], service=ServiceType.TURBINE_DRAIN)
    assert report.by_model[0].label == "HALDEN TD52"
    assert report.by_principle[0].label == "thermodynamic disc"
    assert report.by_service[0].label == "turbine drain"
    assert report.by_pressure[0].label == "MP"


def test_the_worst_model_needs_a_real_sample() -> None:
    report = a_report([("B12-MP-1", [BLOW])])
    assert report.worst_model is None
    bigger = a_report([("B12-MP-1", [BLOW, OK, OK, OK, OK])])
    assert bigger.worst_model is not None
    assert bigger.worst_model.rate == pytest.approx(0.2)


def test_the_worst_principle_is_reported_the_same_way() -> None:
    report = a_report([("B12-MP-1", [BLOW, OK, OK, OK, OK])])
    assert report.worst_principle is not None
    assert report.worst_principle.label == "thermodynamic disc"


def test_repeat_offenders_are_stations_that_failed_more_than_once() -> None:
    report = a_report(
        [
            ("B12-MP-1", [BLOW, BLOW, OK]),
            ("B12-MP-2", [BLOW, OK]),
            ("B12-MP-3", [BLOW, BLOW, BLOW]),
        ]
    )
    assert [str(tag) for tag, _ in report.repeat_offenders] == [
        "B12-MP-0003",
        "B12-MP-0001",
    ]
    assert [str(t) for t in report.stations_failing_at_least(3)] == ["B12-MP-0003"]


def test_asking_for_fewer_than_one_failure_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least once"):
        a_report([("B12-MP-1", [BLOW])]).stations_failing_at_least(0)


def test_a_purchasing_problem_needs_two_models_and_a_gap() -> None:
    good = a_model()
    bad = replace(a_model(), code="TD99")
    register = TrapRegister(
        [
            a_station(tag=TrapTag.parse("B12-MP-1"), model=good),
            a_station(tag=TrapTag.parse("B12-MP-2"), model=bad),
        ]
    )
    history = {
        TrapTag.parse("B12-MP-1"): [OK, OK, OK, OK, OK],
        TrapTag.parse("B12-MP-2"): [BLOW, BLOW, BLOW, BLOW, OK],
    }
    report = build_reliability(register, history)
    assert report.has_a_purchasing_problem
    assert report.by_model[0].label.endswith("TD99")


def test_one_model_alone_is_never_a_purchasing_problem() -> None:
    assert not a_report([("B12-MP-1", [BLOW, BLOW, BLOW, BLOW, BLOW])]).has_a_purchasing_problem


def test_two_models_failing_alike_is_not_a_purchasing_problem() -> None:
    register = TrapRegister(
        [
            a_station(tag=TrapTag.parse("B12-MP-1"), model=a_model()),
            a_station(tag=TrapTag.parse("B12-MP-2"), model=replace(a_model(), code="TD99")),
        ]
    )
    history = {
        TrapTag.parse("B12-MP-1"): [BLOW, OK, OK, OK, OK],
        TrapTag.parse("B12-MP-2"): [BLOW, OK, OK, OK, OK],
    }
    assert not build_reliability(register, history).has_a_purchasing_problem


def test_the_cuts_come_back_worst_first() -> None:
    register = TrapRegister(
        [
            a_station(tag=TrapTag.parse("B12-MP-1"), service=ServiceType.DRIP),
            a_station(tag=TrapTag.parse("B12-MP-2"), service=ServiceType.TRACER),
        ]
    )
    history = {
        TrapTag.parse("B12-MP-1"): [OK, OK],
        TrapTag.parse("B12-MP-2"): [BLOW, BLOW],
    }
    report = build_reliability(register, history)
    assert report.by_service[0].label == "tracer"


def test_a_principle_cut_separates_two_principles() -> None:
    register = TrapRegister(
        [
            a_station(tag=TrapTag.parse("B12-MP-1"), model=a_model()),
            a_station(
                tag=TrapTag.parse("B12-MP-2"),
                model=replace(
                    a_model(), code="FT40", principle=OperatingPrinciple.FLOAT_THERMOSTATIC
                ),
            ),
        ]
    )
    history = {
        TrapTag.parse("B12-MP-1"): [OK],
        TrapTag.parse("B12-MP-2"): [BLOW],
    }
    report = build_reliability(register, history)
    assert [r.label for r in report.by_principle] == [
        "float thermostatic",
        "thermodynamic disc",
    ]


def test_printing_a_rate_and_a_report() -> None:
    assert str(FailureRate("TD52", 10, 3)) == "TD52: 3 of 10 (30%)"
    assert str(FailureRate("TD52", 2, 1)) == "TD52: 1 of 2, too few to rate"
    report = a_report([("B12-MP-1", [BLOW, BLOW])])
    assert str(report) == "1 models, 1 stations failing more than once"
