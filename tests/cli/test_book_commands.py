from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli


def run(book: str, *args: str) -> Result:
    return CliRunner().invoke(cli, ["--book", book, *args])


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = str(tmp_path / "wrx1.sqlite3")
    run(target, "init")
    run(target, "site", "add", "WRX1", "Mill", "--operator", "Bryn")
    run(target, "--site", "WRX1", "area", "add", "B12", "Machine", "--cost-centre", "PM2")
    run(
        target,
        "--site",
        "WRX1",
        "header",
        "add",
        "B12",
        "MP",
        "Main",
        "--psig",
        "125",
        "--discharge-psig",
        "15",
    )
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
    run(target, "--site", "WRX1", "profile", "add", "CONT", "Continuous")
    run(
        target,
        "--site",
        "WRX1",
        "trap",
        "add",
        "B12-MP-1",
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
    )
    return target


def test_a_fresh_book_checks_out(book: str) -> None:
    payload = json.loads(run(book, "--json", "book", "check").output)
    assert payload["integrity"] == "ok"
    assert payload["up_to_date"] is True
    assert payload["schema_version"] == payload["latest_migration"]
    assert len(payload["fingerprint"]) == 12


def test_the_check_counts_the_tables(book: str) -> None:
    payload = json.loads(run(book, "--json", "book", "check").output)
    assert payload["tables"] >= 15
    assert payload["migrations_applied"] == payload["latest_migration"]


def test_a_clean_book_audits_clean(book: str) -> None:
    assert "nothing wrong with this book" in run(book, "--site", "WRX1", "book", "audit").output


def test_a_route_stop_on_an_unknown_tag_is_found(book: str) -> None:
    run(book, "--site", "WRX1", "route", "add", "R1", "Ground floor")
    run(book, "--site", "WRX1", "route", "stop", "R1", "B12-MP-9")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "book", "audit").output)
    assert payload[0]["kind"] == "route stop on an unknown tag"
    assert "B12-MP-0009" in payload[0]["detail"]


def test_an_empty_survey_is_found(book: str) -> None:
    run(
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
    payload = json.loads(run(book, "--site", "WRX1", "--json", "book", "audit").output)
    kinds = {row["kind"] for row in payload}
    assert "survey with no readings" in kinds


def test_a_reading_before_the_trap_went_in_is_found(book: str, tmp_path: Path) -> None:
    run(
        book,
        "--site",
        "WRX1",
        "survey",
        "open",
        "S2019-1",
        "Old",
        "--contractor",
        "Vane",
        "--started",
        "2019-04-07",
    )
    export = tmp_path / "old.csv"
    export.write_text(
        "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
        "B12-MP-1,2019-04-08,R Ellis,pass,32,30,2,350,200,,,,\n",
        encoding="utf-8",
    )
    run(book, "--site", "WRX1", "survey", "import", "S2019-1", str(export))
    payload = json.loads(run(book, "--site", "WRX1", "--json", "book", "audit").output)
    kinds = {row["kind"] for row in payload}
    assert "reading outside the station's life" in kinds


def test_a_trap_under_rated_for_its_header_is_found(book: str) -> None:
    run(
        book,
        "model",
        "add",
        "Halden",
        "LP10",
        "--principle",
        "thermodynamic_disc",
        "--orifice",
        "0.093",
        "--pmo",
        "600",
        "--price",
        "60.00",
    )
    CliRunner().invoke(
        cli,
        [
            "--book",
            book,
            "--site",
            "WRX1",
            "trap",
            "refit",
            "B12-MP-1",
            "--model",
            "Halden/LP10",
            "--on",
            "2025-01-01",
        ],
    )
    run(book, "--site", "WRX1", "book", "audit")
    import sqlite3

    connection = sqlite3.connect(book)
    connection.execute("UPDATE trap_model SET max_operating_psia = 30 WHERE code = 'LP10'")
    connection.commit()
    connection.close()
    payload = json.loads(run(book, "--site", "WRX1", "--json", "book", "audit").output)
    kinds = {row["kind"] for row in payload}
    assert "trap under rated for its header" in kinds


def test_a_work_order_on_a_deleted_station_is_found(book: str) -> None:
    import sqlite3

    connection = sqlite3.connect(book)
    connection.execute(
        "INSERT INTO work_order (number, site_code, tag, action, state, raised_on, "
        "due_on, estimated_cost_cents) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("WO-1", "WRX1", "B12-MP-0099", "repair", "raised", "2025-04-14", "2025-05-14", 100),
    )
    connection.commit()
    connection.close()
    payload = json.loads(run(book, "--site", "WRX1", "--json", "book", "audit").output)
    kinds = {row["kind"] for row in payload}
    assert "work order on an unknown tag" in kinds


def test_a_vacuum_reports_what_it_reclaimed(book: str) -> None:
    payload = json.loads(run(book, "--json", "book", "vacuum").output)
    assert payload["pages_before"] > 0
    assert payload["pages_after"] > 0
    assert payload["bytes_saved"] >= 0


def test_checking_a_book_that_is_not_there(tmp_path: Path) -> None:
    assert run(str(tmp_path / "nope.sqlite3"), "book", "check").exit_code != 0
