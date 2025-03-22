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
    assert "run 'dripleg init'" in str(result.exception)


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
