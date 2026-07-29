from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from dripleg import __version__
from dripleg.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_help_does_not_touch_a_book(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "nothing.sqlite3"
    result = runner.invoke(cli, ["--book", str(target), "--help"])
    assert result.exit_code == 0
    assert "steam loss accounting" in result.output.lower()
    assert not target.exists()


def test_the_version_is_the_package_version(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_makes_the_book(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    result = runner.invoke(cli, ["--book", str(target), "init"])
    assert result.exit_code == 0
    assert "applied 001" in result.output
    assert target.exists()


def test_init_twice_says_it_is_up_to_date(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    runner.invoke(cli, ["--book", str(target), "init"])
    result = runner.invoke(cli, ["--book", str(target), "init"])
    assert result.exit_code == 0
    assert "already up to date" in result.output


def test_init_in_json(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    result = runner.invoke(cli, ["--book", str(target), "--json", "init"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["book"] == str(target)
    assert payload["applied"][0].startswith("001")


def test_about_reports_an_empty_book(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    runner.invoke(cli, ["--book", str(target), "init"])
    result = runner.invoke(cli, ["--book", str(target), "about"])
    assert result.exit_code == 0
    assert "trap stations     0" in result.output
    assert "version" in result.output


def test_about_in_json(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    runner.invoke(cli, ["--book", str(target), "init"])
    result = runner.invoke(cli, ["--book", str(target), "--json", "about"])
    payload = json.loads(result.output)
    assert payload["version"] == __version__
    assert payload["schema_version"] == payload["latest_migration"]
    assert payload["sites"] == 0


def test_about_on_a_book_that_is_not_there(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(cli, ["--book", str(tmp_path / "missing.sqlite3"), "about"])
    assert result.exit_code != 0
    assert "run 'dripleg init'" in result.output


def test_the_book_can_come_from_the_environment(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "env.sqlite3"
    result = runner.invoke(cli, ["init"], env={"DRIPLEG_BOOK": str(target)})
    assert result.exit_code == 0
    assert target.exists()


def test_the_site_option_is_read_back(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    runner.invoke(cli, ["--book", str(target), "init"])
    result = runner.invoke(cli, ["--book", str(target), "--site", "WRX1", "about"])
    assert result.exit_code == 0


def test_about_says_whether_the_book_is_up_to_date(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    runner.invoke(cli, ["--book", str(target), "init"])
    payload = json.loads(runner.invoke(cli, ["--book", str(target), "--json", "about"]).output)
    assert payload["up_to_date"] is True


def test_the_headline_about_is_short(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    runner.invoke(cli, ["--book", str(target), "init"])
    payload = json.loads(runner.invoke(cli, ["--book", str(target), "--json", "about"]).output)
    assert "surveys" not in payload
    assert "routes" not in payload


def test_the_full_about_counts_everything(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    runner.invoke(cli, ["--book", str(target), "init"])
    payload = json.loads(
        runner.invoke(cli, ["--book", str(target), "--json", "about", "--full"]).output
    )
    for key in (
        "areas",
        "headers",
        "routes",
        "surveys",
        "readings",
        "costed_findings",
        "work_orders",
        "open_work_orders",
        "accepted_risks",
        "rules_switched_off",
        "fittings_recorded",
        "site_codes",
    ):
        assert key in payload
    assert payload["site_codes"] == ""


def test_the_full_about_follows_the_book(runner: CliRunner, tmp_path: Path) -> None:
    from tests.support.cli import add_traps, import_survey, make_book, run

    book = make_book(tmp_path, name="full.sqlite3")
    add_traps(book, ["B12-MP-1"])
    import_survey(
        book,
        tmp_path,
        "S2025-1",
        "2025-04-07",
        ["B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,"],
    )
    run(book, "loss", "report", "S2025-1", "--save")
    payload = json.loads(run(book, "--json", "about", "--full").output)
    assert payload["site_codes"] == "WRX1"
    assert payload["surveys"] == 1
    assert payload["readings"] == 1
    assert payload["costed_findings"] == 1
    assert payload["fittings_recorded"] == 1


def test_the_open_orders_are_counted_apart(runner: CliRunner, tmp_path: Path) -> None:
    from tests.support.cli import add_traps, import_survey, make_book, run

    book = make_book(tmp_path, name="orders.sqlite3")
    add_traps(book, ["B12-MP-1"])
    import_survey(
        book,
        tmp_path,
        "S2025-1",
        "2025-04-07",
        ["B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,"],
    )
    run(book, "loss", "report", "S2025-1", "--save")
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    payload = json.loads(run(book, "--json", "about", "--full").output)
    assert payload["work_orders"] == 1
    assert payload["open_work_orders"] == 1
