"""Three surveys on one plant, and the loop closing round them.

The point of this one is the loop rather than any single answer: a trap found
blowing in the spring is repaired, passes in the autumn, and fails again the
following spring, and every report has to tell that story the same way. The
trend puts it in the right bucket, the reliability cut counts it as a repeat
offender, the effectiveness report says the repair did not hold, and the
scorecard's completion figure moves as the jobs are verified.

Three seasons is the smallest number where a repeat offender exists at all,
which is why it is three.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import Result

from tests.support.cli import add_traps, import_survey, make_book, run

SPRING = [
    "B12-MP-1,2025-04-08,R Ellis,failed open,70,30,0,345,258,74,,,",
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,74,,,",
    "B12-MP-3,2025-04-08,R Ellis,cold,4,30,,160,130,74,,,",
]
AUTUMN = [
    "B12-MP-1,2025-10-14,J Pike,pass,32,30,2,350,200,70,,,",
    "B12-MP-2,2025-10-14,J Pike,pass,32,30,2,350,200,70,,,",
    "B12-MP-3,2025-10-14,J Pike,pass,32,30,2,350,200,70,,,",
]
NEXT_SPRING = [
    "B12-MP-1,2026-04-13,R Ellis,failed open,70,30,0,345,258,72,,,",
    "B12-MP-2,2026-04-13,R Ellis,pass,32,30,2,350,200,72,,,",
    "B12-MP-3,2026-04-13,R Ellis,pass,32,30,2,350,200,72,,,",
]


def payload(result: Result) -> object:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.fixture
def plant(tmp_path: Path) -> str:
    """One plant, three traps, three surveys, one repair in between."""

    book = make_book(tmp_path)
    add_traps(book, ["B12-MP-1", "B12-MP-2", "B12-MP-3"])
    run(book, "prices", "set", "--fuel", "6.25", "--from", "2025-01-01")
    import_survey(book, tmp_path, "S2025-1", "2025-04-07", SPRING)
    run(book, "loss", "report", "S2025-1", "--save")
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    for number in ("WO-00001", "WO-00002"):
        run(book, "work", "issue", number, "--to", "A Frayne", "--on", "2025-04-15")
        run(book, "work", "start", number, "--on", "2025-04-18")
        run(book, "work", "complete", number, "--on", "2025-04-18")
    import_survey(book, tmp_path, "S2025-2", "2025-10-13", AUTUMN)
    run(book, "loss", "report", "S2025-2", "--save")
    for number in ("WO-00001", "WO-00002"):
        run(book, "work", "verify", number, "--on", "2025-10-14")
    import_survey(book, tmp_path, "S2026-1", "2026-04-12", NEXT_SPRING)
    run(book, "loss", "report", "S2026-1", "--save")
    return book


def test_the_first_survey_finds_two_of_three_failing(plant: str) -> None:
    report = payload(run(plant, "--json", "survey", "report", "S2025-1"))
    assert isinstance(report, dict)
    assert report["assessed"] == 3
    assert report["conditions"]["blowing through"] == 1
    assert report["conditions"]["failed closed"] == 1


def test_the_repairs_show_as_fixed_in_the_autumn(plant: str) -> None:
    trend = payload(run(plant, "--json", "programme", "compare", "S2025-1", "S2025-2"))
    assert isinstance(trend, dict)
    assert trend["counts"]["fixed"] == 2
    assert trend["counts"]["still failing"] == 0
    assert trend["direction"] == "down"


def test_one_repair_does_not_hold_into_the_next_spring(plant: str) -> None:
    trend = payload(run(plant, "--json", "programme", "compare", "S2025-2", "S2026-1"))
    assert isinstance(trend, dict)
    assert trend["counts"]["newly failed"] == 1
    assert trend["unfixed"] == []


def test_the_effectiveness_report_says_which_repair_came_back(plant: str) -> None:
    rows = payload(run(plant, "--json", "work", "effectiveness"))
    assert isinstance(rows, list)
    outcomes = {row["tag"]: row["outcome"] for row in rows}
    assert outcomes["B12-MP-0001"] == "held"
    assert outcomes["B12-MP-0003"] == "held"


def test_the_trap_that_failed_twice_is_a_repeat_offender(plant: str) -> None:
    repeats = payload(run(plant, "--json", "programme", "repeat-offenders"))
    assert isinstance(repeats, list)
    assert [row["tag"] for row in repeats] == ["B12-MP-0001"]
    assert repeats[0]["failures"] == "2"


def test_the_reliability_cut_sees_all_three_seasons(plant: str) -> None:
    rates = payload(run(plant, "--json", "programme", "reliability"))
    assert isinstance(rates, list)
    assert int(rates[0]["assessed"]) == 9
    assert int(rates[0]["failed"]) == 3


def test_one_traps_whole_costed_history(plant: str) -> None:
    history = payload(run(plant, "--json", "loss", "trap", "B12-MP-1"))
    assert isinstance(history, list)
    assert [row["survey"] for row in history] == ["S2025-1", "S2025-2", "S2026-1"]
    assert [row["rules"] for row in history] == ["blowing through", "ok", "blowing through"]


def test_the_scorecard_shows_the_work_completed(plant: str) -> None:
    card = payload(run(plant, "--json", "programme", "scorecard", "S2026-1", "--on", "2026-05-01"))
    assert isinstance(card, dict)
    measures = {row["name"]: row for row in card["measures"]}
    assert measures["work completed"]["value"] == "100.0%"
    assert measures["backlog accrual"]["value"] == "$0.00"


def test_the_programme_puts_the_failed_trap_back_on_a_short_leash(plant: str) -> None:
    programme = payload(run(plant, "--json", "programme", "due", "--on", "2026-05-01"))
    assert isinstance(programme, dict)
    assert programme["stations"] == 3
    assert programme["never_surveyed"] == 0
    assert programme["shortened"] == 1


def test_the_book_passes_its_own_doctor(plant: str) -> None:
    result = run(plant, "doctor", "--on", "2026-05-01")
    assert result.exit_code == 0


def test_the_failure_count_falls_even_where_the_money_does_not(plant: str) -> None:
    """A cold trap costs nothing and is still a failure, so the two move apart."""

    first = payload(run(plant, "--json", "survey", "report", "S2025-1"))
    last = payload(run(plant, "--json", "survey", "report", "S2026-1"))
    assert isinstance(first, dict)
    assert isinstance(last, dict)
    assert first["failure_rate"] > last["failure_rate"]
    first_cost = payload(run(plant, "--json", "loss", "report", "S2025-1"))
    last_cost = payload(run(plant, "--json", "loss", "report", "S2026-1"))
    assert isinstance(first_cost, dict)
    assert isinstance(last_cost, dict)
    assert last_cost["annual_cost_cents"] == first_cost["annual_cost_cents"]


def test_every_reading_survives_three_seasons(plant: str) -> None:
    readings = payload(run(plant, "--json", "survey", "readings", "B12-MP-1"))
    assert isinstance(readings, list)
    assert [row["date"] for row in readings] == [
        "2025-04-08",
        "2025-10-14",
        "2026-04-13",
    ]
