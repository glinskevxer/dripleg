from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import make_book, run

EXPORT = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,\n"
)


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path, name="wrx1.sqlite3")
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
    return target


@pytest.fixture
def export(tmp_path: Path) -> Path:
    path = tmp_path / "export.csv"
    path.write_text(EXPORT, encoding="utf-8")
    return path


def test_a_survey_is_opened_and_listed(book: str) -> None:
    listed = json.loads(run(book, "--site", "WRX1", "--json", "survey", "list").output)
    assert listed[0]["reference"] == "S2025-1"
    assert listed[0]["finished"] == "open"
    assert listed[0]["readings"] == "0"


def test_opening_the_same_survey_twice_is_refused(book: str) -> None:
    result = run(
        book,
        "--site",
        "WRX1",
        "survey",
        "open",
        "S2025-1",
        "Spring",
        "--contractor",
        "Vane",
        "--started",
        "2025-04-07",
    )
    assert result.exit_code != 0


def test_an_export_imports_into_a_survey(book: str, export: Path) -> None:
    result = run(book, "--site", "WRX1", "--json", "survey", "import", "S2025-1", str(export))
    payload = json.loads(result.output)
    assert payload["profile"] == "fieldbook"
    assert payload["read"] == 2
    assert payload["written"] == 2
    assert payload["quarantined"] == 0
    listed = json.loads(run(book, "--site", "WRX1", "--json", "survey", "list").output)
    assert listed[0]["readings"] == "2"


def test_a_dry_run_writes_nothing(book: str, export: Path) -> None:
    result = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "survey",
        "import",
        "S2025-1",
        str(export),
        "--dry-run",
    )
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["written"] == 0
    listed = json.loads(run(book, "--site", "WRX1", "--json", "survey", "list").output)
    assert listed[0]["readings"] == "0"


def test_a_second_import_amends_rather_than_duplicating(book: str, export: Path) -> None:
    run(book, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    run(book, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    listed = json.loads(run(book, "--site", "WRX1", "--json", "survey", "list").output)
    assert listed[0]["readings"] == "2"


def test_a_bad_row_is_quarantined_and_named(book: str, tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(EXPORT.replace("B12-MP-2", "not a tag"), encoding="utf-8")
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "import", "S2025-1", str(path)).output
    )
    assert payload["read"] == 1
    assert payload["quarantined"] == 1
    assert payload["quarantine"][0].startswith("line 3:")


def test_a_forced_profile_that_does_not_fit_is_refused(book: str, export: Path) -> None:
    result = run(
        book,
        "--site",
        "WRX1",
        "survey",
        "import",
        "S2025-1",
        str(export),
        "--profile",
        "ultraprobe",
    )
    assert result.exit_code != 0


def test_importing_into_a_survey_that_is_not_open(book: str, export: Path) -> None:
    assert run(book, "--site", "WRX1", "survey", "import", "S2099-9", str(export)).exit_code != 0


def test_importing_a_file_that_is_not_there(book: str) -> None:
    assert run(book, "--site", "WRX1", "survey", "import", "S2025-1", "nope.csv").exit_code != 0


def test_a_survey_closes_and_stops_taking_readings(book: str, export: Path) -> None:
    run(book, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    closed = run(book, "--site", "WRX1", "survey", "close", "S2025-1", "--on", "2025-04-11")
    assert closed.exit_code == 0
    assert "2025-04-11" in closed.output
    again = run(book, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    assert again.exit_code != 0


def test_the_survey_report_leads_with_coverage(book: str, export: Path) -> None:
    run(book, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    report = run(book, "--site", "WRX1", "survey", "report", "S2025-1")
    assert report.exit_code == 0
    lines = report.output.splitlines()
    assert lines[0].startswith("S2025-1 Spring: 2 of 2 assessed")
    assert "conditions" in report.output
    assert "parted company" in report.output


def test_the_survey_report_in_json(book: str, export: Path) -> None:
    run(book, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "report", "S2025-1").output
    )
    assert payload["assessed"] == 2
    assert payload["coverage"] == 1.0
    assert payload["disagreements"][0]["rules"] == "blowing through"


def test_an_empty_survey_list_says_so(tmp_path: Path) -> None:
    target = str(tmp_path / "empty.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    assert "no surveys yet" in run(target, "--site", "WRX1", "survey", "list").output
