from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli

EXPORT = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
)


def run(book: str, *args: str) -> Result:
    return CliRunner().invoke(cli, ["--book", book, *args])


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = str(tmp_path / "wrx1.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(target, "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    run(target, "header", "add", "B12", "MP", "Main", "--psig", "125", "--discharge-psig", "15")
    run(
        target,
        "model",
        "add",
        "Halden",
        "TD52",
        "--principle",
        "thermodynamic_disc",
        "--orifice",
        "0.093",
        "--pmo",
        "600",
        "--price",
        "184.00",
    )
    run(target, "profile", "add", "CONT", "Continuous")
    for tag in ("B12-MP-1", "B12-MP-2"):
        run(target, "trap", "add", tag, "--model", "Halden/TD52", "--installed", "2021-06-14")
    run(
        target,
        "survey",
        "open",
        "S2025-1",
        "Spring",
        "--contractor",
        "Vane Energy",
        "--started",
        "2025-04-07",
    )
    export = Path(target).parent / "export.csv"
    export.write_text(EXPORT, encoding="utf-8")
    run(target, "survey", "import", "S2025-1", str(export))
    return target


def test_nothing_is_accepted_to_begin_with(book: str) -> None:
    assert "nothing has been accepted" in run(book, "risk", "list").output


def test_a_finding_can_be_accepted(book: str) -> None:
    accepted = run(
        book,
        "--json",
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "the line comes down in six weeks",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
    )
    payload = json.loads(accepted.output)
    assert payload["tag"] == "B12-MP-0001"
    assert payload["review_on"] == "2026-04-14"
    assert payload["days_left"] == 365


def test_the_review_window_can_be_shortened(book: str) -> None:
    payload = json.loads(
        run(
            book,
            "--json",
            "risk",
            "accept",
            "B12-MP-1",
            "--reason",
            "not now",
            "--by",
            "H Weir",
            "--on",
            "2025-04-14",
            "--months",
            "3",
        ).output
    )
    assert payload["review_on"] == "2025-07-14"


def test_an_accepted_trap_drops_off_the_work_list(book: str) -> None:
    before = json.loads(run(book, "--json", "work", "list", "S2025-1").output)
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "600",
    )
    after = json.loads(run(book, "--json", "work", "list", "S2025-1").output)
    assert before["jobs"] == 2
    assert after["jobs"] == 1
    assert [line["tag"] for line in after["lines"]] == ["B12-MP-0002"]


def test_an_accepted_trap_still_costs_what_it_costs(book: str) -> None:
    before = json.loads(run(book, "--json", "loss", "report", "S2025-1").output)
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "600",
    )
    after = json.loads(run(book, "--json", "loss", "report", "S2025-1").output)
    assert after["annual_cost_cents"] == before["annual_cost_cents"]
    assert after["losing"] == before["losing"]


def test_an_acceptance_can_be_withdrawn(book: str) -> None:
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
    )
    withdrawn = json.loads(run(book, "--json", "risk", "withdraw", "B12-MP-1").output)
    assert withdrawn["was_accepted"] is True
    assert "nothing has been accepted" in run(book, "risk", "list").output


def test_withdrawing_something_that_was_not_accepted(book: str) -> None:
    withdrawn = json.loads(run(book, "--json", "risk", "withdraw", "B12-MP-1").output)
    assert withdrawn["was_accepted"] is False


def test_the_list_shows_live_and_due(book: str) -> None:
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "3",
    )
    live = json.loads(run(book, "--json", "risk", "list", "--on", "2025-05-01").output)
    assert live[0]["state"] == "live"
    due = json.loads(run(book, "--json", "risk", "list", "--on", "2025-08-01").output)
    assert due[0]["state"] == "due"
    assert due[0]["days_left"] == "0"


def test_the_due_only_flag_cuts_the_live_ones(book: str) -> None:
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "3",
    )
    assert (
        "nothing has been accepted"
        in run(book, "risk", "list", "--on", "2025-05-01", "--due-only").output
    )
    due = json.loads(run(book, "--json", "risk", "list", "--on", "2025-08-01", "--due-only").output)
    assert len(due) == 1


def test_accepting_a_trap_that_is_not_a_station(book: str) -> None:
    assert (
        run(book, "risk", "accept", "B12-MP-9", "--reason", "not now", "--by", "H Weir").exit_code
        != 0
    )


def test_a_reason_and_a_name_are_both_required(book: str) -> None:
    assert run(book, "risk", "accept", "B12-MP-1", "--by", "H Weir").exit_code != 0
    assert run(book, "risk", "accept", "B12-MP-1", "--reason", "no").exit_code != 0
