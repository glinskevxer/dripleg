from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from dripleg.cli.main import cli
from tests.support.cli import run


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = tmp_path / "wrx1.sqlite3"
    CliRunner().invoke(cli, ["--book", str(target), "init"])
    return str(target)


def test_a_site_is_added_and_listed(book: str) -> None:
    added = run(book, "site", "add", "WRX1", "Wrexham paper mill", "--operator", "Bryn")
    assert added.exit_code == 0
    assert "Wrexham paper mill" in added.output
    listed = run(book, "site", "list")
    assert "WRX1" in listed.output
    assert "Bryn" in listed.output


def test_an_empty_site_list_says_so(book: str) -> None:
    assert "no sites yet" in run(book, "site", "list").output


def test_a_site_can_be_updated(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(book, "site", "add", "WRX1", "Mill", "--operator", "New Owner", "--start-month", "4")
    listed = run(book, "--json", "site", "list")
    payload = json.loads(listed.output)
    assert len(payload) == 1
    assert payload[0]["operator"] == "New Owner"
    assert payload[0]["start_month"] == "4"


def test_an_area_needs_a_site_once_there_are_two(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(book, "site", "add", "WRX2", "Second mill", "--operator", "Bryn")
    without = run(book, "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    assert without.exit_code != 0
    assert "--site" in str(without.exception)


def test_an_area_needs_no_site_when_there_is_only_one(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    added = run(book, "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    assert added.exit_code == 0


def test_an_area_is_added_and_listed(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    added = run(
        book,
        "--site",
        "WRX1",
        "area",
        "add",
        "B12",
        "Number 2 machine",
        "--cost-centre",
        "pm2",
    )
    assert added.exit_code == 0
    assert "PM2" in added.output
    listed = run(book, "--site", "WRX1", "area", "list")
    assert "Number 2 machine" in listed.output


def test_a_nested_area_names_its_parent(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(book, "--site", "WRX1", "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    run(
        book,
        "--site",
        "WRX1",
        "area",
        "add",
        "B12A",
        "Dryers",
        "--cost-centre",
        "PM2",
        "--parent",
        "B12",
    )
    payload = json.loads(run(book, "--site", "WRX1", "--json", "area", "list").output)
    nested = next(row for row in payload if row["code"] == "B12A")
    assert nested["parent"] == "B12"


def test_an_empty_area_list_says_so(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    assert "no areas yet" in run(book, "--site", "WRX1", "area", "list").output


def test_a_header_is_added_with_its_class_and_saturation(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(book, "--site", "WRX1", "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    added = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "header",
        "add",
        "B12",
        "MP",
        "Machine room main",
        "--psig",
        "125",
        "--discharge-psig",
        "15",
    )
    assert added.exit_code == 0
    payload = json.loads(added.output)
    assert payload["class"] == "MP"
    assert payload["choked"] is True
    assert 350 < payload["saturation_f"] < 356


def test_a_header_list_can_be_cut_to_one_area(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    for area in ("B12", "C3"):
        run(book, "--site", "WRX1", "area", "add", area, f"Area {area}", "--cost-centre", "CC")
        run(
            book,
            "--site",
            "WRX1",
            "header",
            "add",
            area,
            "MP",
            "Main",
            "--psig",
            "125",
        )
    everything = json.loads(run(book, "--site", "WRX1", "--json", "header", "list").output)
    just_one = json.loads(
        run(book, "--site", "WRX1", "--json", "header", "list", "--area", "B12").output
    )
    assert len(everything) == 2
    assert len(just_one) == 1


def test_a_vented_header_keeps_its_destination(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(book, "--site", "WRX1", "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    run(
        book,
        "--site",
        "WRX1",
        "header",
        "add",
        "B12",
        "LP",
        "Vent main",
        "--psig",
        "15",
        "--to",
        "atmosphere",
    )
    payload = json.loads(run(book, "--site", "WRX1", "--json", "header", "list").output)
    assert payload[0]["destination"] == "atmosphere"


def test_a_header_on_an_area_that_is_not_there(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    result = run(book, "--site", "WRX1", "header", "add", "ZZ", "MP", "Main", "--psig", "125")
    assert result.exit_code != 0


def test_an_empty_header_list_says_so(book: str) -> None:
    run(book, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    assert "no headers yet" in run(book, "--site", "WRX1", "header", "list").output
