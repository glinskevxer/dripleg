from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.cli import add_traps, make_book, run


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path)
    run(
        target,
        "model",
        "add",
        "Halden",
        "TD75",
        "--principle",
        "thermodynamic_disc",
        "--orifice",
        "0.093",
        "--pmo",
        "600",
        "--price",
        "96.50",
    )
    add_traps(target, ["B12-MP-1"])
    return target


def test_adding_a_trap_records_the_first_fitting(book: str) -> None:
    payload = json.loads(run(book, "--json", "trap", "history", "B12-MP-1").output)
    assert len(payload) == 1
    assert payload[0]["fitted"] == "2021-06-14"
    assert payload[0]["model"] == "HALDEN TD52"
    assert payload[0]["warranty_ends"] == "2022-06-14"


def test_a_station_nobody_has_fitted_anything_to(book: str) -> None:
    assert "nothing has ever been fitted" in run(book, "trap", "history", "B12-MP-9").output


def test_a_refit_adds_a_second_fitting(book: str) -> None:
    run(
        book,
        "trap",
        "refit",
        "B12-MP-1",
        "--model",
        "Halden/TD75",
        "--on",
        "2025-04-02",
        "--work-order",
        "WO-00001",
    )
    payload = json.loads(run(book, "--json", "trap", "history", "B12-MP-1").output)
    assert len(payload) == 2
    assert payload[1]["model"] == "HALDEN TD75"
    assert payload[1]["work_order"] == "WO-00001"


def test_the_history_is_oldest_first(book: str) -> None:
    run(book, "trap", "refit", "B12-MP-1", "--model", "Halden/TD75", "--on", "2025-04-02")
    payload = json.loads(run(book, "--json", "trap", "history", "B12-MP-1").output)
    assert [row["fitted"] for row in payload] == ["2021-06-14", "2025-04-02"]


def test_nothing_is_under_warranty_years_later(book: str) -> None:
    assert (
        "nothing on this site is still under warranty"
        in run(book, "trap", "warranty", "--on", "2026-01-01").output
    )


def test_a_recent_fitting_is_under_warranty(book: str) -> None:
    run(book, "trap", "refit", "B12-MP-1", "--model", "Halden/TD75", "--on", "2025-04-02")
    payload = json.loads(run(book, "--json", "trap", "warranty", "--on", "2025-06-01").output)
    assert len(payload) == 1
    assert payload[0]["tag"] == "B12-MP-0001"
    assert payload[0]["warranty_ends"] == "2026-04-02"
    assert int(payload[0]["days_left"]) > 0


def test_the_warranty_runs_out(book: str) -> None:
    run(book, "trap", "refit", "B12-MP-1", "--model", "Halden/TD75", "--on", "2025-04-02")
    assert (
        "nothing on this site is still under warranty"
        in run(book, "trap", "warranty", "--on", "2027-01-01").output
    )


def test_the_newest_fitting_decides_the_warranty(book: str) -> None:
    run(book, "trap", "refit", "B12-MP-1", "--model", "Halden/TD75", "--on", "2025-04-02")
    payload = json.loads(run(book, "--json", "trap", "warranty", "--on", "2025-06-01").output)
    assert payload[0]["model"] == "HALDEN TD75"


def test_the_days_in_service_are_counted(book: str) -> None:
    payload = json.loads(run(book, "--json", "trap", "history", "B12-MP-1").output)
    assert int(payload[0]["days_in"]) > 1000


def test_a_refit_on_a_retired_station_records_nothing(book: str) -> None:
    run(book, "trap", "retire", "B12-MP-1", "--on", "2024-03-01")
    assert (
        run(
            book, "trap", "refit", "B12-MP-1", "--model", "Halden/TD75", "--on", "2025-04-02"
        ).exit_code
        != 0
    )
    payload = json.loads(run(book, "--json", "trap", "history", "B12-MP-1").output)
    assert len(payload) == 1
