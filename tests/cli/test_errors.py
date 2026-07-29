from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.cli import add_traps, make_book, run


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path)
    add_traps(target, ["B12-MP-1"])
    return target


def test_a_missing_record_reads_as_an_error_not_a_traceback(book: str) -> None:
    result = run(book, "trap", "show", "B12-MP-9")
    assert result.exit_code == 1
    assert "Error: no trap station with key" in result.output
    assert "Traceback" not in result.output


def test_a_missing_survey_reads_the_same_way(book: str) -> None:
    result = run(book, "loss", "report", "S2099-9")
    assert result.exit_code == 1
    assert "Error: no survey with key" in result.output


def test_a_validation_failure_names_the_field(book: str) -> None:
    result = run(
        book,
        "trap",
        "add",
        "not a tag",
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
    )
    assert result.exit_code == 1
    assert "Error: tag:" in result.output


def test_a_conflict_reads_as_an_error(book: str) -> None:
    run(
        book,
        "survey",
        "open",
        "S2025-1",
        "Spring",
        "--contractor",
        "Vane",
        "--started",
        "2025-04-07",
    )
    result = run(
        book,
        "survey",
        "open",
        "S2025-1",
        "Spring",
        "--contractor",
        "Vane",
        "--started",
        "2025-04-07",
    )
    assert result.exit_code == 1
    assert "already open on this book" in result.output


def test_a_config_failure_reads_as_an_error(tmp_path: Path) -> None:
    result = run(str(tmp_path / "nope.sqlite3"), "about")
    assert result.exit_code == 1
    assert "Error: there is no book at" in result.output


def test_a_bad_option_still_reads_as_a_usage_error(book: str) -> None:
    result = run(book, "trap", "list", "--service", "steamy")
    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_a_command_that_does_not_exist(book: str) -> None:
    result = run(book, "nonsense")
    assert result.exit_code == 2
    assert "No such command" in result.output


def test_a_successful_command_says_nothing_on_the_error_stream(book: str) -> None:
    result = run(book, "trap", "list")
    assert result.exit_code == 0
    assert "Error" not in result.output


def test_the_doctor_still_sets_its_own_exit_code(book: str) -> None:
    run(book, "route", "add", "R1", "Ground floor")
    run(book, "route", "stop", "R1", "B12-MP-9")
    assert run(book, "doctor", "--on", "2026-01-01").exit_code == 1


def test_the_entry_point_returns_a_code_rather_than_raising(
    book: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from dripleg.cli.main import run as entry_point

    monkeypatch.setattr("sys.argv", ["dripleg", "--book", book, "trap", "show", "B12-MP-9"])
    assert entry_point() == 1
    assert "no trap station" in capsys.readouterr().err


def test_the_entry_point_returns_zero_on_success(
    book: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dripleg.cli.main import run as entry_point

    monkeypatch.setattr("sys.argv", ["dripleg", "--book", book, "trap", "list"])
    assert entry_point() == 0


def test_the_entry_point_passes_a_commands_own_exit_code_through(
    book: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dripleg.cli.main import run as entry_point

    run(book, "route", "add", "R1", "Ground floor")
    run(book, "route", "stop", "R1", "B12-MP-9")
    monkeypatch.setattr("sys.argv", ["dripleg", "--book", book, "doctor", "--on", "2026-01-01"])
    assert entry_point() == 1
