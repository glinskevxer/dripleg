from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from dripleg.cli.costing import LOSS_COLUMNS
from tests.support.cli import add_traps, import_survey, make_book, run

READINGS = [
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,",
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,",
]


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path)
    add_traps(target, ["B12-MP-1", "B12-MP-2"])
    import_survey(target, tmp_path, "S2025-1", "2025-04-07", READINGS)
    return target


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_the_export_has_a_row_per_trap(book: str) -> None:
    exported = run(book, "loss", "export", "S2025-1")
    assert exported.exit_code == 0
    parsed = rows(exported.output)
    assert len(parsed) == 2
    assert {row["tag"] for row in parsed} == {"B12-MP-0001", "B12-MP-0002"}


def test_the_header_matches_the_published_columns(book: str) -> None:
    header = run(book, "loss", "export", "S2025-1").output.splitlines()[0]
    assert header.split(",") == list(LOSS_COLUMNS)


def test_the_losing_row_carries_its_numbers(book: str) -> None:
    parsed = {row["tag"]: row for row in rows(run(book, "loss", "export", "S2025-1").output)}
    losing = parsed["B12-MP-0001"]
    assert losing["condition"] == "blowing_through"
    assert float(losing["pounds_per_hour"]) > 0
    assert int(losing["annual_cents"]) > 0
    assert "COR-1" in losing["rules"]
    assert float(losing["share_of_total"]) == pytest.approx(1.0)


def test_the_healthy_row_carries_zeroes(book: str) -> None:
    parsed = {row["tag"]: row for row in rows(run(book, "loss", "export", "S2025-1").output)}
    healthy = parsed["B12-MP-0002"]
    assert healthy["condition"] == "ok"
    assert float(healthy["pounds_per_hour"]) == 0.0
    assert int(healthy["annual_cents"]) == 0
    assert float(healthy["share_of_total"]) == 0.0


def test_the_losing_only_flag_cuts_the_healthy_ones(book: str) -> None:
    parsed = rows(run(book, "loss", "export", "S2025-1", "--losing-only").output)
    assert [row["tag"] for row in parsed] == ["B12-MP-0001"]


def test_the_money_columns_are_whole_cents(book: str) -> None:
    parsed = rows(run(book, "loss", "export", "S2025-1").output)
    for row in parsed:
        assert row["annual_cents"].lstrip("-").isdigit()
        assert row["fuel_cents"].lstrip("-").isdigit()
        assert int(row["annual_cents"]) >= int(row["fuel_cents"])


def test_the_export_carries_the_area_and_the_service(book: str) -> None:
    parsed = rows(run(book, "loss", "export", "S2025-1").output)
    assert all(row["area"] == "B12" for row in parsed)
    assert all(row["service"] == "drip" for row in parsed)


def test_a_survey_with_nothing_on_it_exports_just_the_header(
    tmp_path: Path,
) -> None:
    target = make_book(tmp_path, name="empty.sqlite3")
    run(
        target,
        "survey",
        "open",
        "S2025-9",
        "Empty",
        "--contractor",
        "Vane",
        "--started",
        "2025-04-07",
    )
    lines = run(target, "loss", "export", "S2025-9").output.splitlines()
    assert len(lines) == 1


def test_exporting_a_survey_that_is_not_there(book: str) -> None:
    assert run(book, "loss", "export", "S2099-9").exit_code != 0
