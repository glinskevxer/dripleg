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
    return target


def test_prices_fall_back_to_the_worked_example(book: str) -> None:
    payload = json.loads(run(book, "--site", "WRX1", "--json", "prices", "show").output)
    assert payload["fuel"] == "$6.25/MMBtu"
    assert payload["emissions_factor"] == "natural gas"


def test_prices_can_be_set_and_read_back(book: str) -> None:
    run(
        book,
        "--site",
        "WRX1",
        "prices",
        "set",
        "--fuel",
        "9.4137",
        "--efficiency",
        "0.79",
        "--fuel-type",
        "coal",
        "--from",
        "2025-04-01",
    )
    payload = json.loads(run(book, "--site", "WRX1", "--json", "prices", "show").output)
    assert payload["fuel"] == "$9.4137/MMBtu"
    assert payload["boiler_efficiency"] == 0.79
    assert payload["emissions_factor"] == "bituminous coal"
    assert payload["effective_from"] == "2025-04-01"


def test_an_efficiency_outside_the_range_is_refused(book: str) -> None:
    result = run(book, "--site", "WRX1", "prices", "set", "--fuel", "6.25", "--efficiency", "1.4")
    assert result.exit_code != 0


def test_the_loss_report_prints_the_register(book: str) -> None:
    report = run(book, "--site", "WRX1", "loss", "report", "S2025-1")
    assert report.exit_code == 0
    assert report.output.splitlines()[0].startswith("S2025-1: 1 of 2 traps losing $")
    assert "by area" in report.output
    assert "by condition" in report.output


def test_the_loss_report_in_json(book: str) -> None:
    payload = json.loads(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1").output)
    assert payload["traps"] == 2
    assert payload["losing"] == 1
    assert payload["annual_cost_cents"] > 0
    assert len(payload["top"]) == 1


def test_a_dearer_fuel_makes_a_dearer_report(book: str) -> None:
    cheap = json.loads(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1").output)
    run(book, "--site", "WRX1", "prices", "set", "--fuel", "18.00")
    dear = json.loads(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1").output)
    assert dear["annual_cost_cents"] > cheap["annual_cost_cents"]


def test_the_top_list_is_empty_until_something_is_saved(book: str) -> None:
    assert "nothing costed yet" in run(book, "--site", "WRX1", "loss", "top").output


def test_saving_the_findings_fills_the_top_list(book: str) -> None:
    run(book, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "loss", "top").output)
    assert len(payload) == 1
    assert payload[0]["tag"] == "B12-MP-0001"
    assert payload[0]["condition"] == "blowing through"


def test_the_top_list_can_be_cut_short(book: str) -> None:
    run(book, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    payload = json.loads(
        run(book, "--site", "WRX1", "--json", "loss", "top", "--limit", "0").output
    )
    assert payload == []


def test_one_traps_costed_history(book: str) -> None:
    run(book, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    payload = json.loads(run(book, "--site", "WRX1", "--json", "loss", "trap", "B12-MP-1").output)
    assert len(payload) == 1
    assert payload[0]["survey"] == "S2025-1"
    assert payload[0]["field"] == "ok"
    assert payload[0]["rules"] == "blowing through"


def test_a_trap_with_no_costed_history(book: str) -> None:
    assert (
        "nothing costed on that trap"
        in run(book, "--site", "WRX1", "loss", "trap", "B12-MP-9").output
    )


def test_costing_a_survey_that_is_not_there(book: str) -> None:
    assert run(book, "--site", "WRX1", "loss", "report", "S2099-9").exit_code != 0


def test_the_energy_report_reads_in_fuel_and_carbon(book: str) -> None:
    report = run(book, "loss", "energy", "S2025-1")
    assert report.exit_code == 0
    assert "MMBtu of fuel" in report.output.splitlines()[0]
    assert "makeup water" in report.output
    assert "by area" in report.output


def test_the_energy_report_in_json(book: str) -> None:
    payload = json.loads(run(book, "--json", "loss", "energy", "S2025-1").output)
    assert payload["factor"] == "natural gas"
    assert float(payload["mmbtu"]) > 0
    assert len(payload["traps"]) == 1


def test_the_energy_report_can_be_cut_short(book: str) -> None:
    payload = json.loads(run(book, "--json", "loss", "energy", "S2025-1", "--top", "0").output)
    assert payload["traps"] == []
