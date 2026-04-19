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
    for tag in ("B12-MP-1", "B12-MP-2", "B12-MP-3"):
        run(target, "trap", "add", tag, "--model", "Halden/TD52", "--installed", "2021-06-14")
    run(
        target,
        "survey",
        "open",
        "S2025-1",
        "Spring",
        "--contractor",
        "Vane Energy",
        "--started",
        "2025-04-07",
    )
    export = Path(target).parent / "export.csv"
    export.write_text(EXPORT, encoding="utf-8")
    run(target, "survey", "import", "S2025-1", str(export))
    run(target, "loss", "report", "S2025-1", "--save")
    return target


def measures(book: str, *extra: str) -> dict[str, dict[str, str]]:
    payload = json.loads(run(book, "--json", "programme", "scorecard", "S2025-1", *extra).output)
    return {row["name"]: row for row in payload["measures"]}


def test_the_scorecard_carries_the_six_measures(book: str) -> None:
    found = measures(book, "--on", "2025-06-01")
    assert set(found) == {
        "survey coverage",
        "failure rate",
        "annual loss",
        "work completed",
        "backlog accrual",
        "programme compliance",
    }


def test_coverage_is_off_the_register_not_the_readings(book: str) -> None:
    found = measures(book, "--on", "2025-06-01")
    assert found["survey coverage"]["value"] == "66.7%"


def test_the_failure_rate_is_off_what_was_assessed(book: str) -> None:
    found = measures(book, "--on", "2025-06-01")
    assert found["failure rate"]["value"] == "50.0%"


def test_the_annual_loss_is_the_costed_register(book: str) -> None:
    found = measures(book, "--on", "2025-06-01")
    assert found["annual loss"]["value"].startswith("$")
    assert found["annual loss"]["value"] != "$0.00"


def test_work_completed_is_nothing_before_any_orders(book: str) -> None:
    found = measures(book, "--on", "2025-06-01")
    assert found["work completed"]["value"] == "0.0%"
    assert found["backlog accrual"]["value"] == "$0.00"


def test_raising_a_job_fills_the_backlog(book: str) -> None:
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    found = measures(book, "--on", "2025-08-01")
    assert found["backlog accrual"]["value"] != "$0.00"
    assert found["work completed"]["value"] == "0.0%"


def test_verifying_a_job_moves_the_completion_line(book: str) -> None:
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    run(book, "work", "issue", "WO-00001", "--to", "A Frayne", "--on", "2025-04-15")
    run(book, "work", "start", "WO-00001", "--on", "2025-04-18")
    run(book, "work", "complete", "WO-00001", "--on", "2025-04-18")
    run(book, "work", "verify", "WO-00001", "--on", "2025-05-02")
    found = measures(book, "--on", "2025-08-01")
    assert found["work completed"]["value"] == "100.0%"
    assert found["backlog accrual"]["value"] == "$0.00"


def test_the_programme_compliance_counts_the_unlooked_at(book: str) -> None:
    found = measures(book, "--on", "2025-06-01")
    assert found["programme compliance"]["value"] == "66.7%"
    assert "1 stations have never been surveyed" in found["programme compliance"]["note"]


def test_the_page_reads_as_text_too(book: str) -> None:
    printed = run(book, "programme", "scorecard", "S2025-1", "--on", "2025-06-01")
    assert printed.exit_code == 0
    assert printed.output.splitlines()[0].startswith("WRX1 steam trap programme as at")
    assert "backlog accrual" in printed.output


def test_a_scorecard_for_a_survey_that_is_not_there(book: str) -> None:
    assert run(book, "programme", "scorecard", "S2099-9").exit_code != 0
