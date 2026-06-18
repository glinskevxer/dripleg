"""Two plants on one book, which is how a contractor actually holds them.

The thing being checked is separation. A survey on one site must not appear on
the other, prices set at one must not cost the other, a rule switched off at
one must still run at the other, and the fleet view has to add both up. Every
one of those is a `WHERE site_code = ?` somewhere, and a missing one produces a
report that looks completely reasonable and is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import Result

from tests.support.cli import import_survey, make_book, run

WRX_READINGS = [
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,",
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,,,,",
]
DEE_READINGS = [
    "D4-MP-1,2025-05-12,J Pike,pass,70,30,0,345,258,70,,,",
]


def payload(result: Result) -> object:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.fixture
def book(tmp_path: Path) -> str:
    """One book, two plants, one survey each."""

    target = make_book(tmp_path)
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
    run(target, "site", "add", "DEE2", "Deeside board mill", "--operator", "Bryn Paper")
    run(target, "--site", "DEE2", "area", "add", "D4", "Board machine", "--cost-centre", "BM1")
    run(
        target,
        "--site",
        "DEE2",
        "header",
        "add",
        "D4",
        "MP",
        "Machine main",
        "--psig",
        "125",
        "--discharge-psig",
        "15",
    )
    run(target, "--site", "DEE2", "profile", "add", "CONT", "Continuous")
    run(
        target,
        "--site",
        "DEE2",
        "trap",
        "add",
        "D4-MP-1",
        "--model",
        "Halden/TD52",
        "--installed",
        "2022-02-01",
    )
    import_survey(target, tmp_path, "S2025-1", "2025-04-07", WRX_READINGS, site="WRX1")
    return target


def import_dee(book: str, tmp_path: Path) -> None:
    run(
        book,
        "--site",
        "DEE2",
        "survey",
        "open",
        "D2025-1",
        "Spring",
        "--contractor",
        "Vane Energy",
        "--started",
        "2025-05-11",
    )
    path = tmp_path / "dee.csv"
    path.write_text(
        "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
        + "\n".join(DEE_READINGS)
        + "\n",
        encoding="utf-8",
    )
    run(book, "--site", "DEE2", "survey", "import", "D2025-1", str(path))


def test_each_site_holds_only_its_own_traps(book: str) -> None:
    wrexham = payload(run(book, "--site", "WRX1", "--json", "trap", "list"))
    deeside = payload(run(book, "--site", "DEE2", "--json", "trap", "list"))
    assert isinstance(wrexham, list)
    assert isinstance(deeside, list)
    assert [row["tag"] for row in wrexham] == ["B12-MP-0001", "B12-MP-0002"]
    assert [row["tag"] for row in deeside] == ["D4-MP-0001"]


def test_a_survey_belongs_to_one_site_only(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    wrexham = payload(run(book, "--site", "WRX1", "--json", "survey", "list"))
    deeside = payload(run(book, "--site", "DEE2", "--json", "survey", "list"))
    assert isinstance(wrexham, list)
    assert isinstance(deeside, list)
    assert [row["reference"] for row in wrexham] == ["S2025-1"]
    assert [row["reference"] for row in deeside] == ["D2025-1"]


def test_a_survey_cannot_be_costed_from_the_wrong_site(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    assert run(book, "--site", "WRX1", "loss", "report", "D2025-1").exit_code != 0


def test_prices_set_at_one_site_do_not_move_the_other(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    before = payload(run(book, "--site", "DEE2", "--json", "loss", "report", "D2025-1"))
    run(book, "--site", "WRX1", "prices", "set", "--fuel", "24.00")
    after = payload(run(book, "--site", "DEE2", "--json", "loss", "report", "D2025-1"))
    assert isinstance(before, dict)
    assert isinstance(after, dict)
    assert after["annual_cost_cents"] == before["annual_cost_cents"]


def test_prices_set_at_one_site_do_move_that_one(book: str) -> None:
    before = payload(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1"))
    run(book, "--site", "WRX1", "prices", "set", "--fuel", "24.00")
    after = payload(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1"))
    assert isinstance(before, dict)
    assert isinstance(after, dict)
    assert after["annual_cost_cents"] > before["annual_cost_cents"]


def test_a_rule_switched_off_at_one_site_still_runs_at_the_other(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    for code in ("COR-1", "SND-1", "SND-5", "TMP-1"):
        run(book, "--site", "WRX1", "rules", "off", code, "--reason", "not here")
    wrexham = payload(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1"))
    deeside = payload(run(book, "--site", "DEE2", "--json", "loss", "report", "D2025-1"))
    assert isinstance(wrexham, dict)
    assert isinstance(deeside, dict)
    assert wrexham["losing"] == 0
    assert deeside["losing"] == 1


def test_a_work_order_is_raised_against_one_site(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    run(book, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    wrexham = payload(run(book, "--site", "WRX1", "--json", "work", "open"))
    deeside = payload(run(book, "--site", "DEE2", "--json", "work", "open"))
    assert isinstance(wrexham, list)
    assert len(wrexham) == 1
    assert deeside == []


def test_the_work_order_numbers_do_not_collide_between_sites(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    run(book, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    run(book, "--site", "DEE2", "loss", "report", "D2025-1", "--save")
    run(book, "--site", "WRX1", "work", "raise", "S2025-1", "--on", "2025-04-14")
    run(book, "--site", "DEE2", "work", "raise", "D2025-1", "--on", "2025-05-19")
    wrexham = payload(run(book, "--site", "WRX1", "--json", "work", "open"))
    deeside = payload(run(book, "--site", "DEE2", "--json", "work", "open"))
    assert isinstance(wrexham, list)
    assert isinstance(deeside, list)
    assert len(wrexham) == 1
    assert len(deeside) == 1
    assert wrexham[0]["number"] != deeside[0]["number"]
    assert deeside[0]["tag"] == "D4-MP-0001"


def test_the_fleet_view_adds_both_sites_up(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    run(book, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    run(book, "--site", "DEE2", "loss", "report", "D2025-1", "--save")
    sites = payload(run(book, "--json", "fleet", "sites"))
    assert isinstance(sites, list)
    assert [row["site"] for row in sites] == ["DEE2", "WRX1"]
    rolled = payload(run(book, "--json", "fleet", "total"))
    assert isinstance(rolled, list)
    totals = {row["measure"]: row["value"] for row in rolled}
    assert totals["sites"] == "2"
    assert totals["trap stations"] == "3"
    assert totals["failing at the last survey"] == "2"


def test_a_command_with_two_sites_on_the_book_needs_the_option(book: str) -> None:
    result = run(book, "trap", "list")
    assert result.exit_code != 0
    assert "--site" in str(result.exception)


def test_the_doctor_looks_at_one_site_at_a_time(book: str) -> None:
    wrexham = payload(run(book, "--site", "WRX1", "--json", "doctor", "--on", "2026-01-01"))
    assert isinstance(wrexham, list)
    assert all("D4-" not in row["detail"] for row in wrexham)


def test_an_acceptance_at_one_site_leaves_the_other_alone(book: str, tmp_path: Path) -> None:
    import_dee(book, tmp_path)
    run(
        book,
        "--site",
        "WRX1",
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "coming down",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "600",
    )
    wrexham = payload(run(book, "--site", "WRX1", "--json", "work", "list", "S2025-1"))
    deeside = payload(run(book, "--site", "DEE2", "--json", "work", "list", "D2025-1"))
    assert isinstance(wrexham, dict)
    assert isinstance(deeside, dict)
    assert wrexham["jobs"] == 0
    assert deeside["jobs"] == 1
