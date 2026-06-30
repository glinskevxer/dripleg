from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from tests.support.cli import SURVEY_HEADER, make_book, run

REGISTER = (
    "tag,manufacturer,model,installed\n"
    "B12-MP-1,Halden,TD52,2021-06-14\n"
    "C3-MP-9,Halden,TD52,2021-06-14\n"
)


@pytest.fixture
def book(tmp_path: Path) -> str:
    return make_book(tmp_path)


def rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def test_a_survey_quarantine_file_is_written(book: str, tmp_path: Path) -> None:
    run(
        book,
        "trap",
        "add",
        "B12-MP-1",
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
    )
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
    source = tmp_path / "export.csv"
    source.write_text(
        SURVEY_HEADER
        + "\nB12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,\nrubbish,2025-04-08,R Ellis,pass,,,,,,,,,\n",
        encoding="utf-8",
    )
    target = tmp_path / "quarantine" / "bad.csv"
    result = run(
        book,
        "--json",
        "survey",
        "import",
        "S2025-1",
        str(source),
        "--quarantine",
        str(target),
    )
    payload = json.loads(result.output)
    assert payload["quarantined"] == 1
    assert payload["quarantine_file"] == str(target)
    assert target.exists()
    parsed = rows(target)
    assert parsed[0]["line"] == "3"
    assert "not a trap tag" in parsed[0]["reason"]
    assert parsed[0]["tag"] == "rubbish"


def test_a_clean_survey_import_writes_no_file(book: str, tmp_path: Path) -> None:
    run(
        book,
        "trap",
        "add",
        "B12-MP-1",
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
    )
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
    source = tmp_path / "clean.csv"
    source.write_text(
        SURVEY_HEADER + "\nB12-MP-1,2025-04-08,R Ellis,pass,,,,,,,,,\n", encoding="utf-8"
    )
    target = tmp_path / "bad.csv"
    run(book, "survey", "import", "S2025-1", str(source), "--quarantine", str(target))
    assert not target.exists()


def test_a_register_quarantine_file_is_written(book: str, tmp_path: Path) -> None:
    source = tmp_path / "register.csv"
    source.write_text(REGISTER, encoding="utf-8")
    target = tmp_path / "bad.csv"
    payload = json.loads(
        run(book, "--json", "trap", "import", str(source), "--quarantine", str(target)).output
    )
    assert payload["read"] == 1
    assert payload["quarantined"] == 1
    parsed = rows(target)
    assert parsed[0]["tag"] == "C3-MP-9"
    assert "no header" in parsed[0]["reason"]


def test_the_quarantine_file_can_be_fixed_and_re_imported(book: str, tmp_path: Path) -> None:
    source = tmp_path / "register.csv"
    source.write_text(REGISTER, encoding="utf-8")
    target = tmp_path / "bad.csv"
    run(book, "trap", "import", str(source), "--quarantine", str(target))
    fixed = tmp_path / "fixed.csv"
    fixed.write_text(
        "tag,manufacturer,model,installed\nB12-MP-9,Halden,TD52,2021-06-14\n",
        encoding="utf-8",
    )
    payload = json.loads(run(book, "--json", "trap", "import", str(fixed)).output)
    assert payload["read"] == 1
    assert payload["quarantined"] == 0
    listed = json.loads(run(book, "--json", "trap", "list").output)
    assert len(listed) == 2


def test_a_dry_run_still_writes_the_quarantine(book: str, tmp_path: Path) -> None:
    source = tmp_path / "register.csv"
    source.write_text(REGISTER, encoding="utf-8")
    target = tmp_path / "bad.csv"
    run(book, "trap", "import", str(source), "--quarantine", str(target), "--dry-run")
    assert target.exists()
    assert json.loads(run(book, "--json", "trap", "list").output) == []


def test_the_quarantine_columns_follow_the_source(book: str, tmp_path: Path) -> None:
    source = tmp_path / "register.csv"
    source.write_text(REGISTER, encoding="utf-8")
    target = tmp_path / "bad.csv"
    run(book, "trap", "import", str(source), "--quarantine", str(target))
    header = target.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[:2] == ["line", "reason"]
    assert "manufacturer" in header
