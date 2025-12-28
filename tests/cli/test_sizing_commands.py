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
    return target


def add_trap(book: str, tag: str, *extra: str) -> Result:
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


def test_geometry_goes_on_at_the_command_line(book: str) -> None:
    add_trap(book, "B12-MP-1", "--pipe", "4", "--run-ft", "180", "--warmup-minutes", "45")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "trap", "sizing").output)
    assert len(payload) == 1
    assert payload[0]["pipe"] == "4"
    assert payload[0]["run_ft"] == "180"


def test_half_the_geometry_is_refused(book: str) -> None:
    assert add_trap(book, "B12-MP-1", "--pipe", "4").exit_code != 0
    assert add_trap(book, "B12-MP-2", "--run-ft", "180").exit_code != 0


def test_a_station_without_geometry_is_left_out(book: str) -> None:
    add_trap(book, "B12-MP-1")
    assert (
        "nothing on this register can be sized"
        in run(book, "--site", "WRX1", "trap", "sizing").output
    )


def test_the_sizing_row_carries_both_loads(book: str) -> None:
    add_trap(book, "B12-MP-1", "--pipe", "4", "--run-ft", "180")
    row = json.loads(run(book, "--site", "WRX1", "--json", "trap", "sizing").output)[0]
    assert float(row["warmup_pph"].replace(",", "")) > float(row["running_pph"].replace(",", ""))
    assert float(row["capacity_pph"].replace(",", "")) > 0
    assert row["verdict"] in {"correct", "undersized", "oversized"}


def test_a_long_run_reads_undersized(book: str) -> None:
    add_trap(book, "B12-MP-1", "--pipe", "12", "--run-ft", "600")
    row = json.loads(run(book, "--site", "WRX1", "--json", "trap", "sizing").output)[0]
    assert row["verdict"] == "undersized"


def test_the_wrong_only_flag_cuts_the_healthy_ones(book: str) -> None:
    add_trap(book, "B12-MP-1", "--pipe", "12", "--run-ft", "600")
    add_trap(book, "B12-MP-2", "--pipe", "4", "--run-ft", "180")
    everything = json.loads(run(book, "--site", "WRX1", "--json", "trap", "sizing").output)
    wrong = json.loads(
        run(book, "--site", "WRX1", "--json", "trap", "sizing", "--wrong-only").output
    )
    assert len(everything) == 2
    assert len(wrong) < len(everything)


def test_a_colder_start_makes_a_bigger_warm_up_load(book: str) -> None:
    add_trap(book, "B12-MP-1", "--pipe", "4", "--run-ft", "180")
    warm = json.loads(
        run(book, "--site", "WRX1", "--json", "trap", "sizing", "--cold-f", "100").output
    )[0]
    freezing = json.loads(
        run(book, "--site", "WRX1", "--json", "trap", "sizing", "--cold-f", "20").output
    )[0]
    assert float(freezing["warmup_pph"].replace(",", "")) > float(
        warm["warmup_pph"].replace(",", "")
    )


def test_the_geometry_shows_on_the_station(book: str) -> None:
    add_trap(book, "B12-MP-1", "--pipe", "6", "--run-ft", "240")
    shown = json.loads(run(book, "--site", "WRX1", "--json", "trap", "show", "B12-MP-1").output)
    assert shown["tag"] == "B12-MP-0001"


def test_a_pipe_size_nobody_stocks_is_refused(book: str) -> None:
    add_trap(book, "B12-MP-1", "--pipe", "5", "--run-ft", "180")
    assert run(book, "--site", "WRX1", "trap", "sizing").exit_code != 0
