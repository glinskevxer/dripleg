from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import make_book, run

EXPORT = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,plume\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,\n"
    "B12-MP-3,2025-04-08,J Pike,leaking,32,30,2,350,200,,,,\n"
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
    return target


def test_the_calibration_lists_both_technicians(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "calibration", "S2025-1").output
    )
    names = {row["technician"] for row in payload}
    assert names == {"R Ellis", "J Pike"}


def test_under_calling_shows_against_the_right_person(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "calibration", "S2025-1").output
    )
    ellis = next(row for row in payload if row["technician"] == "R Ellis")
    assert ellis["under_called"] == "1"
    assert ellis["leans"] == "under"


def test_over_calling_shows_against_the_right_person(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "calibration", "S2025-1").output
    )
    pike = next(row for row in payload if row["technician"] == "J Pike")
    assert pike["over_called"] == "1"
    assert pike["leans"] == "over"


def test_a_small_sample_is_not_rated(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "calibration", "S2025-1").output
    )
    assert all(row["agreement"] == "n/a" for row in payload)


def test_the_rated_only_flag_empties_a_small_survey(book: str) -> None:
    listed = run(book, "--site", "WRX1", "survey", "calibration", "S2025-1", "--rated-only")
    assert "nobody has read anything" in listed.output


def test_the_two_method_share_is_reported(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "calibration", "S2025-1").output
    )
    assert all(row["two_method"] == "100%" for row in payload)


def test_the_readings_on_one_trap(book: str) -> None:
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "readings", "B12-MP-1").output
    )
    assert len(payload) == 1
    assert payload[0]["by"] == "R Ellis"
    assert payload[0]["decibels"] == "70"
    assert payload[0]["upstream"] == "345"
    assert payload[0]["note"] == "plume"


def test_a_trap_with_no_readings(book: str) -> None:
    assert (
        "nothing has ever been read"
        in run(book, "--site", "WRX1", "survey", "readings", "B12-MP-9").output
    )


def test_a_reading_with_nothing_measured_prints_blanks(book: str, tmp_path: Path) -> None:
    export = tmp_path / "second.csv"
    export.write_text(
        "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
        "B12-MP-1,2025-10-08,J Pike,missing,,,,,,,,,\n",
        encoding="utf-8",
    )
    run(
        book,
        "--site",
        "WRX1",
        "survey",
        "open",
        "S2025-2",
        "Autumn",
        "--contractor",
        "Vane",
        "--started",
        "2025-10-07",
    )
    run(book, "--site", "WRX1", "survey", "import", "S2025-2", str(export))
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "survey", "readings", "B12-MP-1").output
    )
    assert len(payload) == 2
    assert payload[1]["decibels"] == ""
    assert payload[1]["code"] == "not found"


def test_calibrating_a_survey_that_is_not_there(book: str) -> None:
    assert run(book, "--site", "WRX1", "survey", "calibration", "S2099-9").exit_code != 0
