from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli


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
    for tag in ("B12-MP-1", "B12-MP-2", "B12-MP-3"):
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
    return target


def test_a_route_is_added_and_listed(book: str) -> None:
    added = run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    assert added.exit_code == 0
    listed = json.loads(run(book, "--site", "WRX1", "--json", "route", "list").output)
    assert listed[0]["code"] == "R1"
    assert listed[0]["stops"] == "0"


def test_an_empty_route_list_says_so(book: str) -> None:
    assert "no routes yet" in run(book, "--site", "WRX1", "route", "list").output


def test_stops_go_on_in_order(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    for tag in ("B12-MP-1", "B12-MP-3"):
        run(book, "--site", "WRX1", "route", "stop", "R1", tag)
    added = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "route",
        "stop",
        "R1",
        "B12-MP-2",
        "--after",
        "B12-MP-1",
    )
    assert json.loads(added.output)["stops"] == 3
    shown = json.loads(run(book, "--site", "WRX1", "--json", "route", "show", "R1").output)
    assert [row["tag"] for row in shown] == ["B12-MP-0001", "B12-MP-0002", "B12-MP-0003"]


def test_a_stop_can_be_dropped(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-1")
    dropped = run(book, "--site", "WRX1", "--json", "route", "stop", "R1", "B12-MP-1", "--drop")
    assert json.loads(dropped.output)["stops"] == 0


def test_a_stop_that_is_already_there_is_refused(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-1")
    assert run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-1").exit_code != 0


def test_a_stop_that_is_not_a_station_is_flagged_on_the_walk(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-1")
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-9")
    shown = json.loads(run(book, "--site", "WRX1", "--json", "route", "show", "R1").output)
    assert shown[0]["registered"] == "yes"
    assert shown[1]["registered"] == "no"
    assert shown[1]["service"] == ""


def test_the_timings_drive_the_estimate(book: str) -> None:
    run(
        book,
        "--site",
        "WRX1",
        "route",
        "add",
        "R1",
        "Ground floor",
        "--minutes-per-stop",
        "12",
        "--walk-minutes",
        "60",
    )
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-1")
    facts = json.loads(
        run(book, "--site", "WRX1", "--json", "route", "stop", "R1", "B12-MP-2").output
    )
    assert facts["estimated_hours"] == pytest.approx(1.4)


def test_updating_a_route_keeps_its_stops(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-1")
    facts = json.loads(
        run(
            book,
            "--site",
            "WRX1",
            "--json",
            "route",
            "add",
            "R1",
            "Ground floor",
            "--minutes-per-stop",
            "9",
        ).output
    )
    assert facts["stops"] == 1
    assert facts["minutes_per_stop"] == 9.0


def test_coverage_names_the_traps_nobody_visits(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-1")
    missed = json.loads(run(book, "--site", "WRX1", "--json", "route", "coverage").output)
    assert [row["tag"] for row in missed] == ["B12-MP-0002", "B12-MP-0003"]


def test_full_coverage_says_so(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    for tag in ("B12-MP-1", "B12-MP-2", "B12-MP-3"):
        run(book, "--site", "WRX1", "route", "stop", "R1", tag)
    assert "every trap is on a route" in run(book, "--site", "WRX1", "route", "coverage").output


def test_a_route_splits_across_days(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    for tag in ("B12-MP-1", "B12-MP-2", "B12-MP-3"):
        run(book, "--site", "WRX1", "route", "stop", "R1", tag)
    pieces = json.loads(
        run(book, "--site", "WRX1", "--json", "route", "split", "R1", "--days", "2").output
    )
    assert [row["stops"] for row in pieces] == ["2", "1"]
    assert pieces[0]["from"] == "B12-MP-0001"
    assert pieces[1]["to"] == "B12-MP-0003"


def test_splitting_into_no_days_is_refused(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    assert run(book, "--site", "WRX1", "route", "split", "R1", "--days", "0").exit_code != 0


def test_showing_a_route_that_is_not_there(book: str) -> None:
    assert run(book, "--site", "WRX1", "route", "show", "R9").exit_code != 0
