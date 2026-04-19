from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from dripleg.cli.main import cli
from tests.support.cli import run


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = str(tmp_path / "wrx1.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(target, "--site", "WRX1", "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    return target


def test_a_one_site_book_needs_no_site_option(book: str) -> None:
    listed = run(book, "--json", "area", "list")
    assert listed.exit_code == 0
    assert json.loads(listed.output)[0]["code"] == "B12"


def test_a_second_site_makes_the_option_required(book: str) -> None:
    run(book, "site", "add", "WRX2", "Second mill", "--operator", "Bryn")
    result = run(book, "area", "list")
    assert result.exit_code != 0
    assert "this book holds WRX1, WRX2" in str(result.exception)


def test_the_option_still_works_with_two_sites(book: str) -> None:
    run(book, "site", "add", "WRX2", "Second mill", "--operator", "Bryn")
    listed = run(book, "--site", "WRX1", "--json", "area", "list")
    assert listed.exit_code == 0
    assert len(json.loads(listed.output)) == 1


def test_a_book_with_no_sites_says_to_add_one(tmp_path: Path) -> None:
    target = str(tmp_path / "empty.sqlite3")
    run(target, "init")
    result = run(target, "area", "list")
    assert result.exit_code != 0
    assert "no sites on it yet" in str(result.exception)


def test_the_environment_variable_still_wins(book: str) -> None:
    run(book, "site", "add", "WRX2", "Second mill", "--operator", "Bryn")
    result = CliRunner().invoke(
        cli, ["--book", book, "--json", "area", "list"], env={"DRIPLEG_SITE": "WRX1"}
    )
    assert result.exit_code == 0


def test_the_fallback_works_for_every_group(book: str) -> None:
    for command in (
        ["header", "list"],
        ["trap", "list"],
        ["route", "list"],
        ["survey", "list"],
        ["profile", "list"],
        ["prices", "show"],
    ):
        assert run(book, *command).exit_code == 0
