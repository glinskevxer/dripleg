from __future__ import annotations

from dripleg.report.scorecard import ScoreLine, build_scorecard
from dripleg.units.money import Money


def a_scorecard(**overrides: object):  # type: ignore[no-untyped-def]
    fields: dict[str, object] = {
        "coverage": 0.92,
        "failure_rate": 0.14,
        "annual_cost": Money.from_dollars("41250.00"),
        "jobs_raised": 20,
        "jobs_verified": 14,
        "backlog_cost": Money.from_dollars("6100.00"),
        "programme_compliance": 0.81,
        "never_surveyed": 12,
    }
    fields.update(overrides)
    return build_scorecard("WRX1", "2026-01-31", "S2025-2", **fields)  # type: ignore[arg-type]


def test_the_headline_names_the_site_and_the_survey() -> None:
    card = a_scorecard()
    assert card.headline == ("WRX1 steam trap programme as at 2026-01-31 (S2025-2)")


def test_the_six_measures_are_all_there() -> None:
    names = [line.name for line in a_scorecard().lines_in]
    assert names == [
        "survey coverage",
        "failure rate",
        "annual loss",
        "work completed",
        "backlog accrual",
        "programme compliance",
    ]


def test_the_percentages_are_formatted() -> None:
    card = a_scorecard()
    coverage = card.find("survey coverage")
    failures = card.find("failure rate")
    assert coverage is not None
    assert failures is not None
    assert coverage.value == "92.0%"
    assert failures.value == "14.0%"


def test_the_work_completed_line_is_verified_over_raised() -> None:
    line = a_scorecard().find("work completed")
    assert line is not None
    assert line.value == "70.0%"
    assert "14 of 20 jobs verified" in line.note


def test_a_programme_with_no_jobs_raised_reads_zero() -> None:
    line = a_scorecard(jobs_raised=0, jobs_verified=0).find("work completed")
    assert line is not None
    assert line.value == "0.0%"


def test_the_money_lines_carry_no_target() -> None:
    card = a_scorecard()
    for name in ("annual loss", "backlog accrual"):
        line = card.find(name)
        assert line is not None
        assert not line.has_target
        assert line.value.startswith("$")


def test_the_percentage_lines_carry_targets() -> None:
    card = a_scorecard()
    for name in ("survey coverage", "failure rate", "work completed"):
        line = card.find(name)
        assert line is not None
        assert line.has_target


def test_a_measure_nobody_asked_for() -> None:
    assert a_scorecard().find("something else") is None


def test_the_table_has_one_row_per_measure() -> None:
    card = a_scorecard()
    assert len(card.table()) == len(card.lines_in)


def test_the_rendered_page_leads_with_the_headline() -> None:
    card = a_scorecard()
    assert card.render().splitlines()[0] == card.headline
    assert "backlog accrual" in card.render()


def test_the_json_shape_carries_every_measure() -> None:
    payload = a_scorecard().as_dict()
    assert payload["site"] == "WRX1"
    measures = payload["measures"]
    assert isinstance(measures, list)
    assert len(measures) == 6
    assert set(measures[0]) == {"name", "value", "target", "note"}


def test_printing_a_line_with_and_without_a_target() -> None:
    assert str(ScoreLine("coverage", "92.0%", "95%")) == "coverage: 92.0% (target 95%)"
    assert str(ScoreLine("annual loss", "$41,250.00")) == "annual loss: $41,250.00"
