from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli

EXPORT = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,\n"
)


def run(book: str, *args: str) -> Result:
    return CliRunner().invoke(cli, ["--book", book, *args])


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = str(tmp_path / "wrx1.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(target, "--site", "WRX1", "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    run(
        target,
        "--site",
        "WRX1",
        "header",
        "add",
        "B12",
        "MP",
        "Main",
        "--psig",
        "125",
        "--discharge-psig",
        "15",
    )
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
    run(target, "--site", "WRX1", "profile", "add", "CONT", "Continuous")
    for tag in ("B12-MP-1", "B12-MP-2"):
        run(
            target,
            "--site",
            "WRX1",
            "trap",
            "add",
            tag,
            "--model",
            "Halden/TD52",
            "--installed",
            "2021-06-14",
        )
    run(
        target,
        "--site",
        "WRX1",
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
    run(target, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    return target


def test_the_work_list_ranks_the_jobs(book: str) -> None:
    listed = run(book, "--site", "WRX1", "work", "list", "S2025-1")
    assert listed.exit_code == 0
    assert listed.output.splitlines()[0].startswith("WRX1: 1 jobs")
    assert "B12-MP-0001" in listed.output
    assert "pays back in" in listed.output


def test_the_work_list_in_json(book: str) -> None:
    payload = json.loads(run(book, "--site", "WRX1", "--json", "work", "list", "S2025-1").output)
    assert payload["jobs"] == 1
    assert payload["lines"][0]["tag"] == "B12-MP-0001"
    assert payload["lines"][0]["action"] == "repair"


def test_a_budget_draws_a_line(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "list", "S2025-1", "--budget", "1.00").output
    )
    assert payload["budget_cents"] == 100
    assert payload["lines"][0]["inside_budget"] is False


def test_a_band_filter_can_empty_the_list(book: str) -> None:
    payload = json.loads(
        run(
            book, "--site", "WRX1", "--json", "work", "list", "S2025-1", "--band", "deferred"
        ).output
    )
    assert payload["jobs"] == 0


def test_orders_are_raised_from_the_list(book: str) -> None:
    raised = run(book, "--site", "WRX1", "--json", "work", "raise", "S2025-1", "--on", "2025-04-14")
    payload = json.loads(raised.output)
    assert len(payload) == 1
    assert payload[0]["number"] == "WO-00001"
    assert payload[0]["tag"] == "B12-MP-0001"
    assert payload[0]["action"] == "repair"


def test_raising_twice_does_not_duplicate_an_open_order(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    again = run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-15")
    assert "nothing to raise" in again.output
    payload = json.loads(run(book, "--site", "WRX1", "--json", "work", "open").output)
    assert len(payload) == 1


def test_a_budget_limits_what_is_raised(book: str) -> None:
    raised = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "work",
        "raise",
        "S2025-1",
        "--on",
        "2025-04-14",
        "--budget",
        "1.00",
    )
    assert json.loads(raised.output) == []


def test_an_order_runs_through_to_verified(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    run(
        book,
        "--site",
        "WRX1",
        "work",
        "issue",
        "WO-00001",
        "--to",
        "A Frayne",
        "--on",
        "2025-04-15",
    )
    run(book, "--site", "WRX1", "work", "start", "WO-00001", "--on", "2025-04-18")
    completed = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "work",
        "complete",
        "WO-00001",
        "--on",
        "2025-04-18",
        "--cost",
        "151.20",
    )
    payload = json.loads(completed.output)
    assert payload["state"] == "done"
    assert payload["actual"] == "$151.20"
    verified = run(
        book, "--site", "WRX1", "--json", "work", "verify", "WO-00001", "--on", "2025-05-02"
    )
    assert json.loads(verified.output)["state"] == "verified"
    assert "nothing open" in run(book, "--site", "WRX1", "work", "open").output


def test_an_order_cannot_skip_a_step(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    result = run(book, "--site", "WRX1", "work", "complete", "WO-00001", "--on", "2025-04-18")
    assert result.exit_code != 0


def test_the_open_list_can_be_cut_to_the_late_ones(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    early = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "open", "--overdue-on", "2025-04-20").output
    )
    late = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "open", "--overdue-on", "2026-04-20").output
    )
    assert early == []
    assert len(late) == 1


def test_the_order_history_is_kept(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    run(
        book,
        "--site",
        "WRX1",
        "work",
        "issue",
        "WO-00001",
        "--to",
        "A Frayne",
        "--on",
        "2025-04-15",
    )
    payload = json.loads(
        run(
            book, "--site", "WRX1", "--json", "work", "start", "WO-00001", "--on", "2025-04-18"
        ).output
    )
    assert len(payload["history"]) == 2
    assert "issued to A Frayne" in payload["history"][0]


def test_moving_an_order_that_is_not_there(book: str) -> None:
    result = run(book, "--site", "WRX1", "work", "start", "WO-99999", "--on", "2025-04-18")
    assert result.exit_code != 0
