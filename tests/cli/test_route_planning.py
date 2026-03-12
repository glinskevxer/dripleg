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
    for area in ("B12", "C3"):
        run(target, "area", "add", area, f"Area {area}", "--cost-centre", "CC")
        run(target, "header", "add", area, "MP", "Main", "--psig", "125", "--discharge-psig", "15")
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
    for tag in ("B12-MP-1", "B12-MP-2", "B12-MP-3", "C3-MP-1"):
        run(
            target,
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
        "trap",
        "add",
        "C3-MP-2",
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
        "--access",
        "scaffold_required",
    )
    return target


def test_the_plan_groups_by_area_and_system(book: str) -> None:
    payload = json.loads(run(book, "--json", "route", "plan").output)
    assert [row["name"] for row in payload] == ["B12 MP", "C3 MP"]
    assert payload[0]["stops"] == "3"
    assert payload[0]["from"] == "B12-MP-0001"
    assert payload[0]["to"] == "B12-MP-0003"


def test_the_hard_to_reach_trap_is_left_off(book: str) -> None:
    payload = json.loads(run(book, "--json", "route", "plan").output)
    assert sum(int(row["stops"]) for row in payload) == 4


def test_a_short_shift_cuts_the_area_into_parts(book: str) -> None:
    payload = json.loads(
        run(
            book,
            "--json",
            "route",
            "plan",
            "--shift-hours",
            "0.5",
            "--walk-minutes",
            "10",
            "--minutes-per-stop",
            "10",
        ).output
    )
    names = [row["name"] for row in payload]
    assert "B12 MP part 1" in names
    assert "B12 MP part 2" in names


def test_the_plan_writes_nothing_unless_asked(book: str) -> None:
    run(book, "route", "plan")
    assert "no routes yet" in run(book, "route", "list").output


def test_saving_the_plan_puts_the_routes_on_the_book(book: str) -> None:
    run(book, "route", "plan", "--save")
    routes = json.loads(run(book, "--json", "route", "list").output)
    assert [row["code"] for row in routes] == ["R01", "R02"]
    stops = json.loads(run(book, "--json", "route", "show", "R01").output)
    assert [row["tag"] for row in stops] == [
        "B12-MP-0001",
        "B12-MP-0002",
        "B12-MP-0003",
    ]


def test_the_prefix_can_be_changed(book: str) -> None:
    payload = json.loads(run(book, "--json", "route", "plan", "--prefix", "WALK").output)
    assert payload[0]["code"] == "WALK01"


def test_a_shift_that_fits_nothing_is_refused(book: str) -> None:
    assert run(book, "route", "plan", "--shift-hours", "0.2", "--walk-minutes", "30").exit_code != 0


def test_the_arrange_list_names_what_needs_setting_up(book: str) -> None:
    payload = json.loads(run(book, "--json", "route", "arrange").output)
    assert payload[0]["access"] == "scaffold_required"
    assert payload[0]["tags"] == "C3-MP-0002"


def test_a_register_everybody_can_reach_needs_nothing_arranged(tmp_path: Path) -> None:
    target = str(tmp_path / "easy.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    assert "every trap can be walked up to" in run(target, "route", "arrange").output


def test_an_empty_register_plans_nothing(tmp_path: Path) -> None:
    target = str(tmp_path / "empty.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    assert "there is nothing to route" in run(target, "route", "plan").output


def test_the_planned_routes_cover_everything_the_coverage_check_wants(book: str) -> None:
    run(book, "route", "plan", "--save")
    missed = json.loads(run(book, "--json", "route", "coverage").output)
    assert [row["tag"] for row in missed] == ["C3-MP-0002"]
