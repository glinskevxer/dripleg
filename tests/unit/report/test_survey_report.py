from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.report.survey_report import SurveyReport, build_survey_report
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from tests.support.build import DAY, a_station, pipe, probe

BLOWING = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}


def a_report(
    tags: list[str],
    readings: list[tuple[str, TrapCondition, dict[str, object]]],
    *,
    closed: bool = True,
) -> SurveyReport:
    register = TrapRegister([a_station(tag=TrapTag.parse(tag)) for tag in tags])
    survey = Survey(
        "WRX1", "S2025-1", "Spring machine room", "Vane Energy", DAY - dt.timedelta(days=1)
    )
    for tag, condition, fields in readings:
        survey.record(
            Observation(
                tag=TrapTag.parse(tag),
                observed_on=DAY,
                technician="R Ellis",
                reported_condition=condition,
                **fields,  # type: ignore[arg-type]
            )
        )
    if closed:
        survey.close(DAY + dt.timedelta(days=2))
    return build_survey_report(register, survey, diagnose_survey(register, survey))


def a_full_report() -> SurveyReport:
    return a_report(
        ["B12-MP-1", "B12-MP-2", "B12-MP-3", "B12-MP-4"],
        [
            ("B12-MP-1", TrapCondition.OK, BLOWING),
            ("B12-MP-2", TrapCondition.OK, HEALTHY),
            ("B12-MP-3", TrapCondition.NOT_FOUND, {}),
        ],
    )


def test_the_headline_leads_with_coverage() -> None:
    report = a_full_report()
    assert report.headline.startswith("S2025-1 Spring machine room: 2 of 4 assessed")
    assert report.coverage == pytest.approx(0.5)


def test_the_summary_carries_the_counts() -> None:
    lines = "\n".join(a_full_report().summary_lines())
    assert "contractor    Vane Energy" in lines
    assert "on register   4" in lines
    assert "assessed      2 (50.0%)" in lines
    assert "not found     1" in lines


def test_the_dates_show_open_where_a_survey_is_open() -> None:
    report = a_report(["B12-MP-1"], [("B12-MP-1", TrapCondition.OK, HEALTHY)], closed=False)
    assert report.finished_on == "open"
    assert "to open" in "\n".join(report.summary_lines())


def test_the_condition_table_is_worst_first_and_shares_add_up() -> None:
    table = a_full_report().condition_table()
    lines = table.lines()
    assert "blowing through" in lines[2]
    assert len(table) == 3


def test_the_disagreement_block_lists_where_they_parted() -> None:
    report = a_full_report()
    assert ("B12-MP-0001", "ok", "blowing through") in report.disagreements
    assert len(report.disagreements) == 1
    rendered = report.render()
    assert "parted company" in rendered


def test_a_report_with_no_disagreements_leaves_the_block_out() -> None:
    report = a_report(["B12-MP-1"], [("B12-MP-1", TrapCondition.OK, HEALTHY)])
    assert report.disagreements == []
    assert "parted company" not in report.render()


def test_readings_that_could_not_be_judged_are_listed() -> None:
    report = a_report(
        ["B12-MP-1"],
        [
            ("B12-MP-1", TrapCondition.OK, HEALTHY),
            ("B12-MP-9", TrapCondition.OK, HEALTHY),
        ],
    )
    assert report.skipped == ["B12-MP-0009"]
    assert "could not be judged" in report.render()


def test_a_clean_report_leaves_the_skipped_block_out() -> None:
    report = a_report(["B12-MP-1"], [("B12-MP-1", TrapCondition.OK, HEALTHY)])
    assert report.skipped == []
    assert "could not be judged" not in report.render()


def test_the_failure_and_agreement_rates_are_carried_through() -> None:
    report = a_full_report()
    assert report.failure_rate == pytest.approx(0.5)
    assert report.agreement_rate == pytest.approx(2 / 3)


def test_an_empty_register_has_no_coverage() -> None:
    report = a_report([], [])
    assert report.coverage == 0.0
    assert report.on_register == 0


def test_the_json_shape_carries_everything_the_text_does() -> None:
    payload = a_full_report().as_dict()
    assert payload["reference"] == "S2025-1"
    assert payload["on_register"] == 4
    assert payload["assessed"] == 2
    assert payload["coverage"] == pytest.approx(0.5)
    assert payload["skipped"] == []
    assert isinstance(payload["conditions"], dict)
    assert payload["disagreements"] == [
        {"tag": "B12-MP-0001", "field": "ok", "rules": "blowing through"}
    ]


def test_the_rendered_report_is_one_string() -> None:
    rendered = a_full_report().render()
    assert rendered.count("\n") == len(a_full_report().lines()) - 1
    assert rendered.splitlines()[0] == a_full_report().headline


def test_the_condition_table_of_an_empty_survey() -> None:
    report = a_report(["B12-MP-1"], [])
    table = report.condition_table()
    assert table.is_empty
    assert len(table.lines()) == 2
