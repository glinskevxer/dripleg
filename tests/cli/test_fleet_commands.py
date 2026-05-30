from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import add_traps, import_survey, make_book, run

READINGS = [
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,",
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,",
]


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path)
    add_traps(target, ["B12-MP-1", "B12-MP-2"])
    import_survey(target, tmp_path, "S2025-1", "2025-04-07", READINGS)
    run(target, "loss", "report", "S2025-1", "--save")
    return target


def second_site(book: str) -> None:
    run(book, "site", "add", "WRX2", "Second mill", "--operator", "Bryn Paper")
    run(book, "--site", "WRX2", "area", "add", "D4", "Second area", "--cost-centre", "CC2")
    run(
        book,
        "--site",
        "WRX2",
        "header",
        "add",
        "D4",
        "MP",
        "Main",
        "--psig",
        "125",
        "--discharge-psig",
        "15",
    )
    run(book, "--site", "WRX2", "profile", "add", "CONT", "Continuous")
    run(
        book,
        "--site",
        "WRX2",
        "trap",
        "add",
        "D4-MP-1",
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
    )


def test_one_site_lists_on_its_own(book: str) -> None:
    payload = json.loads(run(book, "--json", "fleet", "sites").output)
    assert len(payload) == 1
    assert payload[0]["site"] == "WRX1"
    assert payload[0]["traps"] == "2"
    assert payload[0]["last_survey"] == "S2025-1"
    assert payload[0]["failing"] == "1"


def test_the_annual_loss_comes_off_the_last_survey(book: str) -> None:
    payload = json.loads(run(book, "--json", "fleet", "sites").output)
    assert payload[0]["annual"].startswith("$")
    assert payload[0]["annual"] != "$0.00"


def test_a_second_site_appears_beside_the_first(book: str) -> None:
    second_site(book)
    payload = json.loads(run(book, "--json", "fleet", "sites").output)
    assert [row["site"] for row in payload] == ["WRX1", "WRX2"]
    assert payload[1]["traps"] == "1"
    assert payload[1]["surveys"] == "0"
    assert payload[1]["last_survey"] == ""


def test_a_site_with_no_survey_costs_nothing(book: str) -> None:
    second_site(book)
    payload = json.loads(run(book, "--json", "fleet", "sites").output)
    assert payload[1]["annual"] == "$0.00"
    assert payload[1]["failing"] == "0"


def test_the_open_jobs_are_counted_per_site(book: str) -> None:
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    payload = json.loads(run(book, "--json", "fleet", "sites").output)
    assert payload[0]["open_jobs"] == "1"


def test_the_total_adds_the_sites_up(book: str) -> None:
    second_site(book)
    payload = {
        row["measure"]: row["value"]
        for row in json.loads(run(book, "--json", "fleet", "total").output)
    }
    assert payload["sites"] == "2"
    assert payload["trap stations"] == "3"
    assert payload["failing at the last survey"] == "1"
    assert payload["annual loss"].startswith("$")


def test_the_total_counts_the_open_jobs(book: str) -> None:
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    payload = {
        row["measure"]: row["value"]
        for row in json.loads(run(book, "--json", "fleet", "total").output)
    }
    assert payload["open jobs"] == "1"


def test_an_empty_book_says_so(tmp_path: Path) -> None:
    target = str(tmp_path / "empty.sqlite3")
    run(target, "init")
    assert "this book holds no sites" in run(target, "fleet", "sites").output
    assert "this book holds no sites" not in run(target, "fleet", "total").output


def test_the_fleet_commands_need_no_site_option(book: str) -> None:
    second_site(book)
    assert run(book, "fleet", "sites").exit_code == 0
    assert run(book, "fleet", "total").exit_code == 0
