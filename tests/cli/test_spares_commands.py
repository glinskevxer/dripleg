from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli

EXPORT = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
    "B12-MP-3,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,\n"
)


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


def test_the_spares_list_rolls_the_jobs_up(book: str) -> None:
    payload = json.loads(run(book, "--site", "WRX1", "--json", "work", "spares", "S2025-1").output)
    assert len(payload) == 1
    assert payload[0]["code"] == "TD52"
    assert payload[0]["part"] == "repair kit"
    assert payload[0]["jobs"] == "2"


def test_the_allowance_can_be_turned_off(book: str) -> None:
    payload = json.loads(
        run(
            book,
            "--site",
            "WRX1",
            "--json",
            "work",
            "spares",
            "S2025-1",
            "--allowance",
            "0",
        ).output
    )
    assert payload[0]["quantity"] == "2"


def test_a_big_allowance_orders_more(book: str) -> None:
    payload = json.loads(
        run(
            book,
            "--site",
            "WRX1",
            "--json",
            "work",
            "spares",
            "S2025-1",
            "--allowance",
            "0.5",
        ).output
    )
    assert payload[0]["quantity"] == "3"


def test_a_budget_cuts_the_parts_list_too(book: str) -> None:
    payload = json.loads(
        run(
            book,
            "--site",
            "WRX1",
            "--json",
            "work",
            "spares",
            "S2025-1",
            "--budget",
            "1.00",
        ).output
    )
    assert payload == []


def test_a_healthy_survey_needs_no_parts(book: str, tmp_path: Path) -> None:
    export = tmp_path / "clean.csv"
    export.write_text(
        "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
        "B12-MP-1,2025-10-08,J Pike,pass,32,30,2,350,200,,,,\n",
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
    assert (
        "the list needs no parts" in run(book, "--site", "WRX1", "work", "spares", "S2025-2").output
    )


def test_the_line_total_is_the_unit_price_times_the_quantity(book: str) -> None:
    payload = json.loads(
        run(
            book,
            "--site",
            "WRX1",
            "--json",
            "work",
            "spares",
            "S2025-1",
            "--allowance",
            "0",
        ).output
    )
    unit = float(payload[0]["unit_price"].lstrip("$").replace(",", ""))
    total = float(payload[0]["total"].lstrip("$").replace(",", ""))
    assert total == pytest.approx(unit * 2)


def test_a_daft_allowance_is_refused(book: str) -> None:
    assert (
        run(book, "--site", "WRX1", "work", "spares", "S2025-1", "--allowance", "2").exit_code != 0
    )


def test_spares_for_a_survey_that_is_not_there(book: str) -> None:
    assert run(book, "--site", "WRX1", "work", "spares", "S2099-9").exit_code != 0
