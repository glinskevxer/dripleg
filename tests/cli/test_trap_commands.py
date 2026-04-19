from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import Result

from tests.support.cli import make_book, run


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path, name="wrx1.sqlite3")
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
    return target


def add_trap(book: str, tag: str = "B12-MP-43", *extra: str) -> Result:
    return run(
        book,
        "--site",
        "WRX1",
        "trap",
        "add",
        tag,
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
        *extra,
    )


def test_a_trap_is_added_and_shown(book: str) -> None:
    added = add_trap(book)
    assert added.exit_code == 0
    assert "B12-MP-0043" in added.output
    shown = run(book, "--site", "WRX1", "--json", "trap", "show", "B12-MP-43")
    payload = json.loads(shown.output)
    assert payload["model"] == "HALDEN TD52"
    assert payload["principle"] == "thermodynamic disc"
    assert payload["discharges_to"] == "return"
    assert payload["can_be_isolated"] is True


def test_a_trap_takes_its_header_pressure_from_the_book(book: str) -> None:
    add_trap(book)
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "show", "B12-MP-43").output)
    assert payload["pressure"] == "125.0 psig"


def test_the_service_sets_the_survey_interval(book: str) -> None:
    add_trap(book, "B12-MP-43", "--service", "tracer")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "show", "B12-MP-43").output)
    assert payload["service"] == "tracer"
    assert payload["interval_months"] == 24


def test_an_interval_override_wins(book: str) -> None:
    add_trap(book, "B12-MP-43", "--service", "tracer", "--interval", "3")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "show", "B12-MP-43").output)
    assert payload["interval_months"] == 3


def test_a_station_with_no_valves_cannot_be_isolated(book: str) -> None:
    add_trap(book, "B12-MP-43", "--valves", "0")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "show", "B12-MP-43").output)
    assert payload["can_be_isolated"] is False


def test_a_trap_can_override_the_header_destination(book: str) -> None:
    add_trap(book, "B12-MP-43", "--to", "atmosphere")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "show", "B12-MP-43").output)
    assert payload["discharges_to"] == "atmosphere"


def test_traps_list_and_filter(book: str) -> None:
    add_trap(book, "B12-MP-1")
    add_trap(book, "B12-MP-2", "--service", "tracer")
    everything = json.loads(run(book, "--site", "WRX1", "--json", "trap", "list").output)
    tracers = json.loads(
        run(book, "--site", "WRX1", "--json", "trap", "list", "--service", "tracer").output
    )
    assert len(everything) == 2
    assert len(tracers) == 1
    assert tracers[0]["tag"] == "B12-MP-0002"


def test_traps_can_be_cut_to_one_area(book: str) -> None:
    add_trap(book, "B12-MP-1")
    in_area = json.loads(
        run(book, "--site", "WRX1", "--json", "trap", "list", "--area", "B12").output
    )
    elsewhere = json.loads(
        run(book, "--site", "WRX1", "--json", "trap", "list", "--area", "C3").output
    )
    assert len(in_area) == 1
    assert elsewhere == []


def test_an_empty_register_says_so(book: str) -> None:
    assert "no traps yet" in run(book, "--site", "WRX1", "trap", "list").output


def test_a_retired_trap_drops_out_of_the_live_list(book: str) -> None:
    add_trap(book, "B12-MP-1")
    retired = run(book, "--site", "WRX1", "trap", "retire", "B12-MP-1", "--on", "2024-03-01")
    assert retired.exit_code == 0
    assert "2024-03-01" in retired.output
    live = json.loads(run(book, "--site", "WRX1", "--json", "trap", "list", "--live").output)
    assert live == []
    everything = json.loads(run(book, "--site", "WRX1", "--json", "trap", "list").output)
    assert len(everything) == 1


def test_refitting_keeps_the_station_and_changes_the_trap(book: str) -> None:
    add_trap(book, "B12-MP-1")
    refitted = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "trap",
        "refit",
        "B12-MP-1",
        "--model",
        "Halden/TD75",
        "--on",
        "2025-04-02",
    )
    payload = json.loads(refitted.output)
    assert payload["model"] == "HALDEN TD75"
    assert payload["installed_on"] == "2025-04-02"


def test_refitting_a_retired_station_is_refused(book: str) -> None:
    add_trap(book, "B12-MP-1")
    run(book, "--site", "WRX1", "trap", "retire", "B12-MP-1", "--on", "2024-03-01")
    result = run(
        book,
        "--site",
        "WRX1",
        "trap",
        "refit",
        "B12-MP-1",
        "--model",
        "Halden/TD75",
        "--on",
        "2025-04-02",
    )
    assert result.exit_code != 0


def test_a_trap_on_a_header_that_is_not_there(book: str) -> None:
    result = run(
        book,
        "--site",
        "WRX1",
        "trap",
        "add",
        "C3-MP-1",
        "--model",
        "Halden/TD52",
        "--installed",
        "2021-06-14",
    )
    assert result.exit_code != 0


def test_a_trap_on_a_model_that_is_not_there(book: str) -> None:
    result = run(
        book,
        "--site",
        "WRX1",
        "trap",
        "add",
        "B12-MP-1",
        "--model",
        "Halden/NOPE",
        "--installed",
        "2021-06-14",
    )
    assert result.exit_code != 0


def test_showing_a_trap_that_is_not_there(book: str) -> None:
    assert run(book, "--site", "WRX1", "trap", "show", "B12-MP-99").exit_code != 0
