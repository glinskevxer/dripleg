from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_every_assumption_is_listed(book: str) -> None:
    payload = json.loads(run(book, "--json", "loss", "sensitivity", "S2025-1", "B12-MP-1").output)
    names = {row["assumption"] for row in payload}
    assert names == {
        "open fraction of the seat",
        "live hours a year",
        "boiler efficiency",
        "condensate returned",
        "fuel price",
    }


def test_the_widest_swing_comes_first(book: str) -> None:
    payload = json.loads(run(book, "--json", "loss", "sensitivity", "S2025-1", "B12-MP-1").output)
    swings = [float(row["swing"].rstrip("%")) for row in payload]
    assert swings == sorted(swings, reverse=True)


def test_the_base_cost_is_the_same_on_every_row(book: str) -> None:
    payload = json.loads(run(book, "--json", "loss", "sensitivity", "S2025-1", "B12-MP-1").output)
    assert len({row["base_cost"] for row in payload}) == 1


def test_the_fuel_price_row_doubles(book: str) -> None:
    payload = json.loads(run(book, "--json", "loss", "sensitivity", "S2025-1", "B12-MP-1").output)
    fuel = next(row for row in payload if row["assumption"] == "fuel price")
    base = float(fuel["base_cost"].lstrip("$").replace(",", ""))
    high = float(fuel["high_cost"].lstrip("$").replace(",", ""))
    assert high == pytest.approx(base * 2, rel=0.001)


def test_a_healthy_trap_has_nothing_to_move(book: str) -> None:
    assert "losing nothing" in run(book, "loss", "sensitivity", "S2025-1", "B12-MP-2").output


def test_a_trap_that_was_not_costed(book: str) -> None:
    assert run(book, "loss", "sensitivity", "S2025-1", "B12-MP-9").exit_code != 0


def test_the_text_form_reads_as_a_table(book: str) -> None:
    printed = run(book, "loss", "sensitivity", "S2025-1", "B12-MP-1")
    assert printed.exit_code == 0
    assert "assumption" in printed.output
    assert "fuel price" in printed.output


def test_a_survey_that_is_not_there(book: str) -> None:
    assert run(book, "loss", "sensitivity", "S2099-9", "B12-MP-1").exit_code != 0
