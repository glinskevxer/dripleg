from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import make_book, run

SPRING = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,\n"
)
AUTUMN = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-10-08,J Pike,pass,70,30,0,345,258,74,,,\n"
)


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path, name="wrx1.sqlite3")
    for tag in ("B12-MP-1", "B12-MP-2", "B12-MP-3"):
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
    for reference, started, text in (
        ("S2025-1", "2025-04-07", SPRING),
        ("S2025-2", "2025-10-07", AUTUMN),
    ):
        run(
            target,
            "--site",
            "WRX1",
            "survey",
            "open",
            reference,
            "Season",
            "--contractor",
            "Vane Energy",
            "--started",
            started,
        )
        path = Path(target).parent / f"{reference}.csv"
        path.write_text(text, encoding="utf-8")
        run(target, "--site", "WRX1", "survey", "import", reference, str(path))
        run(target, "--site", "WRX1", "loss", "report", reference, "--save")
    return target


def test_the_programme_report_names_both_kinds_of_gap(book: str) -> None:
    report = run(book, "--site", "WRX1", "programme", "due", "--on", "2026-06-01")
    assert report.exit_code == 0
    assert "compliant" in report.output.splitlines()[0]
    assert "never surveyed" in report.output
    assert "B12-MP-0003" in report.output


def test_the_programme_report_in_json(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "programme", "due", "--on", "2026-06-01").output
    )
    assert payload["stations"] == 3
    assert payload["never_surveyed"] == 1
    assert payload["overdue"] >= 1
    assert payload["compliance"] < 1.0
    assert len(payload["workload"]) == 12


def test_a_failed_trap_is_on_a_short_leash(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "programme", "due", "--on", "2025-11-01").output
    )
    assert payload["shortened"] == 1


def test_nothing_is_overdue_right_after_a_survey(book: str) -> None:
    listed = run(book, "--site", "WRX1", "programme", "overdue", "--on", "2025-10-10")
    assert "nothing overdue" in listed.output


def test_the_overdue_list_fills_up_later(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "programme", "overdue", "--on", "2027-01-01").output
    )
    assert len(payload) == 2
    assert int(payload[0]["days_late"]) >= int(payload[1]["days_late"])


def test_the_reliability_cut_by_model(book: str) -> None:
    payload = json.loads(run(book, "--site", "WRX1", "--json", "programme", "reliability").output)
    assert payload[0]["model"] == "HALDEN TD52"
    assert int(payload[0]["assessed"]) == 3
    assert int(payload[0]["failed"]) == 2


def test_a_small_sample_is_not_rated(book: str) -> None:
    payload = json.loads(run(book, "--site", "WRX1", "--json", "programme", "reliability").output)
    assert payload[0]["rate"] == "n/a"


def test_the_reliability_cut_can_be_changed(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "programme", "reliability", "--by", "service").output
    )
    assert payload[0]["service"] == "drip"


def test_the_repeat_offenders(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "programme", "repeat-offenders").output
    )
    assert len(payload) == 1
    assert payload[0]["tag"] == "B12-MP-0001"
    assert payload[0]["failures"] == "2"


def test_asking_for_more_failures_than_anybody_has(book: str) -> None:
    listed = run(book, "--site", "WRX1", "programme", "repeat-offenders", "--at-least", "5")
    assert "no station has failed that often" in listed.output


def test_a_book_with_no_findings_still_answers(tmp_path: Path) -> None:
    target = str(tmp_path / "empty.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    payload = json.loads(
        run(target, "--site", "WRX1", "--json", "programme", "due", "--on", "2026-01-01").output
    )
    assert payload["stations"] == 0
    assert payload["compliance"] == 1.0
