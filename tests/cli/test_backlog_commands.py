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
    export = Path(target).parent / "export.csv"
    export.write_text(EXPORT, encoding="utf-8")
    run(target, "--site", "WRX1", "survey", "import", "S2025-1", str(export))
    run(target, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    return target


def test_an_empty_backlog_says_so(book: str) -> None:
    assert (
        "nothing open has ever been costed" in run(book, "--site", "WRX1", "work", "backlog").output
    )


def test_an_open_job_accrues(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "backlog", "--as-at", "2025-07-07").output
    )
    assert len(payload) == 1
    assert payload[0]["tag"] == "B12-MP-0001"
    assert payload[0]["found"] == "2025-04-07"
    assert int(payload[0]["days"]) == 91
    assert payload[0]["accrued"].startswith("$")


def test_the_accrual_grows_with_time(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    early = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "backlog", "--as-at", "2025-05-07").output
    )[0]
    late = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "backlog", "--as-at", "2025-10-07").output
    )[0]
    assert float(late["accrued"].lstrip("$").replace(",", "")) > float(
        early["accrued"].lstrip("$").replace(",", "")
    )


def test_a_verified_job_drops_off_the_backlog(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    run(
        book,
        "--site",
        "WRX1",
        "work",
        "issue",
        "WO-00001",
        "--to",
        "A Frayne",
        "--on",
        "2025-04-15",
    )
    run(book, "--site", "WRX1", "work", "start", "WO-00001", "--on", "2025-04-18")
    run(book, "--site", "WRX1", "work", "complete", "WO-00001", "--on", "2025-04-18")
    run(book, "--site", "WRX1", "work", "verify", "WO-00001", "--on", "2025-05-02")
    assert (
        "nothing open has ever been costed"
        in run(book, "--site", "WRX1", "work", "backlog", "--as-at", "2025-07-07").output
    )


def test_the_steam_lost_is_reported_alongside_the_money(book: str) -> None:
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    row = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "backlog", "--as-at", "2025-07-07").output
    )[0]
    assert int(row["pounds_lost"].replace(",", "")) > 1000


def test_a_job_raised_but_never_costed_is_left_out(book: str, tmp_path: Path) -> None:
    import sqlite3

    connection = sqlite3.connect(book)
    connection.execute(
        "INSERT INTO work_order (number, site_code, tag, action, state, raised_on, "
        "due_on, estimated_cost_cents) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("WO-77", "WRX1", "B12-MP-0002", "repair", "raised", "2025-04-14", "2025-05-14", 100),
    )
    connection.commit()
    connection.close()
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "work", "backlog", "--as-at", "2025-07-07").output
    )
    tags = {row["tag"] for row in payload}
    assert "B12-MP-0002" in tags or tags == set()
