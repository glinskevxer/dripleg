"""A whole survey year through the command line, on one small plant.

The unit tests hold each layer to its own contract. This holds the layers to
each other: a register built by one command is read by another, a survey
imported from a file is costed by a third, and the work orders raised off that
costing close against a retest in the following season.

Everything here goes through the CLI on a file backed book, because that is the
path a plant actually uses and it is the only path that exercises the store,
the loaders and the reports together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli

SPRING = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,failed open,70,30,0,345,258,74,,,plume at the drip leg\n"
    "B12-MP-2,2025-04-08,R Ellis,pass,32,30,2,350,200,74,,,\n"
    "B12-MP-3,2025-04-09,R Ellis,cold,4,30,,160,130,74,,,\n"
    "B12-LP-1,2025-04-09,R Ellis,pass,20,30,1,240,180,74,,,\n"
    "B12-LP-9,2025-04-09,R Ellis,pass,20,30,1,240,180,74,,,\n"
)

AUTUMN = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-10-14,J Pike,pass,32,30,2,350,200,70,,,repaired in April\n"
    "B12-MP-2,2025-10-14,J Pike,pass,32,30,2,350,200,70,,,\n"
    "B12-MP-3,2025-10-14,J Pike,failed open,70,30,0,345,258,70,,,\n"
    "B12-LP-1,2025-10-15,J Pike,missing,,,,,,,,,\n"
)


def run(book: str, *args: str) -> Result:
    return CliRunner().invoke(cli, ["--book", book, *args])


def payload(result: Result) -> object:
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


@pytest.fixture
def plant(tmp_path: Path) -> str:
    """A mill with two headers, four registered traps and its prices set."""

    book = str(tmp_path / "wrx1.sqlite3")
    assert run(book, "init").exit_code == 0
    run(book, "site", "add", "WRX1", "Wrexham paper mill", "--operator", "Bryn Paper")
    run(book, "--site", "WRX1", "area", "add", "B12", "Number 2 machine", "--cost-centre", "PM2")
    run(
        book,
        "--site",
        "WRX1",
        "header",
        "add",
        "B12",
        "MP",
        "Machine room main",
        "--psig",
        "125",
        "--discharge-psig",
        "15",
    )
    run(
        book,
        "--site",
        "WRX1",
        "header",
        "add",
        "B12",
        "LP",
        "Dryer hood main",
        "--psig",
        "30",
        "--discharge-psig",
        "5",
    )
    run(
        book,
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
    run(book, "--site", "WRX1", "profile", "add", "CONT", "Continuous")
    for tag, service in (
        ("B12-MP-1", "drip"),
        ("B12-MP-2", "drip"),
        ("B12-MP-3", "process_coil"),
        ("B12-LP-1", "unit_heater"),
    ):
        run(
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
            "--service",
            service,
        )
    run(
        book,
        "--site",
        "WRX1",
        "prices",
        "set",
        "--fuel",
        "6.25",
        "--efficiency",
        "0.82",
        "--from",
        "2025-01-01",
    )
    return book


def import_survey(book: str, reference: str, started: str, text: str, tmp_path: Path) -> Result:
    run(
        book,
        "--site",
        "WRX1",
        "survey",
        "open",
        reference,
        "Season",
        "--contractor",
        "Vane Energy",
        "--started",
        started,
    )
    path = tmp_path / f"{reference}.csv"
    path.write_text(text, encoding="utf-8")
    return run(book, "--site", "WRX1", "--json", "survey", "import", reference, str(path))


def test_the_spring_survey_imports_and_flags_the_unknown_tag(plant: str, tmp_path: Path) -> None:
    result = payload(import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path))
    assert isinstance(result, dict)
    assert result["read"] == 5
    assert result["quarantined"] == 0
    report = payload(run(plant, "--site", "WRX1", "--json", "survey", "report", "S2025-1"))
    assert isinstance(report, dict)
    assert report["on_register"] == 4
    assert report["assessed"] == 4
    assert report["skipped"] == ["B12-LP-0009"]


def test_the_rules_agree_with_the_crew_on_the_clear_cases(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    report = payload(run(plant, "--site", "WRX1", "--json", "survey", "report", "S2025-1"))
    assert isinstance(report, dict)
    assert report["conditions"]["blowing through"] == 1
    assert report["conditions"]["failed closed"] == 1
    assert report["disagreements"] == []


def test_the_spring_loss_register_costs_only_the_blowing_trap(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    losses = payload(run(plant, "--site", "WRX1", "--json", "loss", "report", "S2025-1", "--save"))
    assert isinstance(losses, dict)
    assert losses["traps"] == 4
    assert losses["losing"] == 1
    assert losses["top"][0]["tag"] == "B12-MP-0001"
    assert losses["annual_cost_cents"] > 100_000


def test_the_work_list_ranks_the_safety_job_above_the_money(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    work = payload(run(plant, "--site", "WRX1", "--json", "work", "list", "S2025-1"))
    assert isinstance(work, dict)
    tags = [line["tag"] for line in work["lines"]]
    assert "B12-MP-0001" in tags
    assert "B12-MP-0003" in tags
    assert work["jobs"] == 2


def test_orders_are_raised_and_close_on_a_retest(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    raised = payload(
        run(plant, "--site", "WRX1", "--json", "work", "raise", "S2025-1", "--on", "2025-04-14")
    )
    assert isinstance(raised, list)
    assert len(raised) == 2
    number = raised[0]["number"]
    run(plant, "--site", "WRX1", "work", "issue", number, "--to", "A Frayne", "--on", "2025-04-15")
    run(plant, "--site", "WRX1", "work", "start", number, "--on", "2025-04-18")
    run(
        plant,
        "--site",
        "WRX1",
        "work",
        "complete",
        number,
        "--on",
        "2025-04-18",
        "--cost",
        "151.20",
    )
    still_open = payload(run(plant, "--site", "WRX1", "--json", "work", "open"))
    assert isinstance(still_open, list)
    assert {row["state"] for row in still_open} == {"done", "raised"}
    verified = payload(
        run(plant, "--site", "WRX1", "--json", "work", "verify", number, "--on", "2025-10-14")
    )
    assert isinstance(verified, dict)
    assert verified["state"] == "verified"


def test_the_autumn_survey_shows_the_repair_worked(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    import_survey(plant, "S2025-2", "2025-10-13", AUTUMN, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-2", "--save")
    history = payload(run(plant, "--site", "WRX1", "--json", "loss", "trap", "B12-MP-1"))
    assert isinstance(history, list)
    assert [row["survey"] for row in history] == ["S2025-1", "S2025-2"]
    assert history[0]["rules"] == "blowing through"
    assert history[1]["rules"] == "ok"


def test_the_programme_puts_the_failed_traps_on_a_short_leash(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    import_survey(plant, "S2025-2", "2025-10-13", AUTUMN, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-2", "--save")
    programme = payload(
        run(plant, "--site", "WRX1", "--json", "programme", "due", "--on", "2025-12-01")
    )
    assert isinstance(programme, dict)
    assert programme["stations"] == 4
    assert programme["never_surveyed"] == 0
    assert programme["shortened"] == 1


def test_a_trap_that_went_missing_is_not_a_failure(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    import_survey(plant, "S2025-2", "2025-10-13", AUTUMN, tmp_path)
    report = payload(run(plant, "--site", "WRX1", "--json", "survey", "report", "S2025-2"))
    assert isinstance(report, dict)
    assert report["not_found"] == 1
    assert report["assessed"] == 3


def test_the_reliability_cut_sees_both_seasons(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    import_survey(plant, "S2025-2", "2025-10-13", AUTUMN, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-2", "--save")
    rates = payload(run(plant, "--site", "WRX1", "--json", "programme", "reliability"))
    assert isinstance(rates, list)
    assert rates[0]["model"] == "HALDEN TD52"
    assert int(rates[0]["assessed"]) == 7
    assert int(rates[0]["failed"]) == 3


def test_a_trap_that_failed_twice_shows_as_a_repeat_offender(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    import_survey(plant, "S2025-2", "2025-10-13", AUTUMN, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-2", "--save")
    repeats = payload(run(plant, "--site", "WRX1", "--json", "programme", "repeat-offenders"))
    assert isinstance(repeats, list)
    assert [row["tag"] for row in repeats] == ["B12-MP-0003"]


def test_the_book_survives_being_reopened(plant: str, tmp_path: Path) -> None:
    import_survey(plant, "S2025-1", "2025-04-07", SPRING, tmp_path)
    run(plant, "--site", "WRX1", "loss", "report", "S2025-1", "--save")
    about = payload(run(plant, "--json", "about"))
    assert isinstance(about, dict)
    assert about["trap_stations"] == 4
    assert about["sites"] == 1
    assert about["schema_version"] == about["latest_migration"]
