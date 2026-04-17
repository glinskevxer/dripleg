from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli

SPRING = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
)
AUTUMN = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-10-08,J Pike,pass,32,30,2,350,200,,,,\n"
    "B12-MP-2,2025-10-08,J Pike,pass,70,30,0,345,258,70,,,\n"
)


def run(book: str, *args: str) -> Result:
    return CliRunner().invoke(cli, ["--book", book, *args])


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = str(tmp_path / "wrx1.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(target, "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    run(target, "header", "add", "B12", "MP", "Main", "--psig", "125", "--discharge-psig", "15")
    run(
        target,
        "model",
        "add",
        "Halden",
        "TD52",
        "--principle",
        "thermodynamic_disc",
        "--orifice",
        "0.093",
        "--pmo",
        "600",
        "--price",
        "184.00",
    )
    run(target, "profile", "add", "CONT", "Continuous")
    for tag in ("B12-MP-1", "B12-MP-2"):
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
    export = Path(target).parent / "spring.csv"
    export.write_text(SPRING, encoding="utf-8")
    run(target, "survey", "import", "S2025-1", str(export))
    run(target, "loss", "report", "S2025-1", "--save")
    return target


def raise_and_finish(book: str) -> None:
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    for number in ("WO-00001", "WO-00002"):
        run(book, "work", "issue", number, "--to", "A Frayne", "--on", "2025-04-15")
        run(book, "work", "start", number, "--on", "2025-04-18")
        run(book, "work", "complete", number, "--on", "2025-04-18")


def import_autumn(book: str, tmp_path: Path) -> None:
    run(
        book,
        "survey",
        "open",
        "S2025-2",
        "Autumn",
        "--contractor",
        "Vane Energy",
        "--started",
        "2025-10-07",
    )
    export = tmp_path / "autumn.csv"
    export.write_text(AUTUMN, encoding="utf-8")
    run(book, "survey", "import", "S2025-2", str(export))
    run(book, "loss", "report", "S2025-2", "--save")


def test_nothing_finished_says_so(book: str) -> None:
    assert "no repair has been finished yet" in run(book, "work", "effectiveness").output


def test_a_finished_repair_is_unproven_until_the_next_survey(book: str) -> None:
    raise_and_finish(book)
    payload = json.loads(run(book, "--json", "work", "effectiveness").output)
    assert len(payload) == 2
    assert all(row["outcome"] == "unproven" for row in payload)
    assert all(row["next_survey"] == "" for row in payload)


def test_the_next_survey_settles_each_repair(book: str, tmp_path: Path) -> None:
    raise_and_finish(book)
    import_autumn(book, tmp_path)
    payload = json.loads(run(book, "--json", "work", "effectiveness").output)
    outcomes = {row["tag"]: row["outcome"] for row in payload}
    assert outcomes["B12-MP-0001"] == "held"
    assert outcomes["B12-MP-0002"] == "came back"


def test_the_outcome_filter_cuts_the_list(book: str, tmp_path: Path) -> None:
    raise_and_finish(book)
    import_autumn(book, tmp_path)
    held = json.loads(run(book, "--json", "work", "effectiveness", "--outcome", "held").output)
    back = json.loads(run(book, "--json", "work", "effectiveness", "--outcome", "came back").output)
    assert [row["tag"] for row in held] == ["B12-MP-0001"]
    assert [row["tag"] for row in back] == ["B12-MP-0002"]


def test_the_row_carries_what_the_next_survey_found(book: str, tmp_path: Path) -> None:
    raise_and_finish(book)
    import_autumn(book, tmp_path)
    payload = json.loads(run(book, "--json", "work", "effectiveness").output)
    came_back = next(row for row in payload if row["tag"] == "B12-MP-0002")
    assert came_back["found"] == "blowing through"
    assert came_back["next_survey"] == "2025-10-07"


def test_a_verified_order_is_still_assessed(book: str, tmp_path: Path) -> None:
    raise_and_finish(book)
    run(book, "work", "verify", "WO-00001", "--on", "2025-05-02")
    import_autumn(book, tmp_path)
    payload = json.loads(run(book, "--json", "work", "effectiveness").output)
    assert len(payload) == 2


def test_a_cancelled_order_is_left_out(book: str) -> None:
    run(book, "work", "raise", "S2025-1", "--on", "2025-04-14")
    payload = json.loads(run(book, "--json", "work", "effectiveness").output)
    assert payload == []
