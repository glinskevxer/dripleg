from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = tmp_path / "wrx1.sqlite3"
    runner = CliRunner()
    runner.invoke(cli, ["--book", str(target), "init"])
    runner.invoke(cli, ["--book", str(target), "site", "add", "WRX1", "Mill", "--operator", "Bryn"])
    return str(target)


def run(book: str, *args: str) -> Result:
    return CliRunner().invoke(cli, ["--book", book, *args])


def add_model(book: str, code: str = "TD52", *extra: str) -> Result:
    return run(
        book,
        "model",
        "add",
        "Halden",
        code,
        "--principle",
        "thermodynamic_disc",
        "--orifice",
        "0.093",
        "--pmo",
        "600",
        "--price",
        "184.00",
        *extra,
    )


def test_a_model_is_added_and_listed(book: str) -> None:
    added = add_model(book)
    assert added.exit_code == 0
    assert "HALDEN" in added.output
    listed = run(book, "model", "list")
    assert "TD52" in listed.output
    assert "thermodynamic disc" in listed.output


def test_a_model_reports_what_it_is_rated_for(book: str) -> None:
    add_model(book)
    row = json.loads(run(book, "--json", "model", "list").output)[0]
    assert row["pmo_psig"] == "600"
    assert row["orifice_in"] == "0.093"
    assert row["stocked"] == "yes"


def test_an_empty_catalogue_says_so(book: str) -> None:
    assert "no models yet" in run(book, "model", "list").output


def test_the_catalogue_can_be_cut_to_one_principle(book: str) -> None:
    add_model(book, "TD52")
    run(
        book,
        "model",
        "add",
        "Halden",
        "FT40",
        "--principle",
        "float_thermostatic",
        "--orifice",
        "0.25",
        "--pmo",
        "200",
        "--price",
        "265.00",
    )
    everything = json.loads(run(book, "--json", "model", "list").output)
    discs = json.loads(
        run(book, "--json", "model", "list", "--principle", "thermodynamic_disc").output
    )
    assert len(everything) == 2
    assert len(discs) == 1


def test_a_discontinued_model_is_marked(book: str) -> None:
    add_model(book, "TD52", "--discontinued", "--replaced-by", "TD75")
    row = json.loads(run(book, "--json", "model", "list").output)[0]
    assert row["stocked"] == "no"


def test_a_bad_price_is_refused(book: str) -> None:
    result = run(
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
        "free",
    )
    assert result.exit_code != 0


def test_a_principle_nobody_stocks_is_refused(book: str) -> None:
    result = run(
        book,
        "model",
        "add",
        "Halden",
        "TD52",
        "--principle",
        "magic",
        "--orifice",
        "0.093",
        "--pmo",
        "600",
        "--price",
        "1",
    )
    assert result.exit_code != 0
    assert "magic" in result.output


def test_a_profile_is_added_and_listed(book: str) -> None:
    added = run(book, "--site", "WRX1", "profile", "add", "CONT", "Continuous")
    assert added.exit_code == 0
    listed = run(book, "--site", "WRX1", "profile", "list")
    assert "CONT" in listed.output
    assert "8,760" in listed.output


def test_a_seasonal_profile_reports_fewer_hours(book: str) -> None:
    run(
        book,
        "--site",
        "WRX1",
        "profile",
        "add",
        "HEAT",
        "Building heating",
        "--pattern",
        "heating_season",
    )
    row = json.loads(run(book, "--site", "WRX1", "--json", "profile", "list").output)[0]
    assert int(row["hours_per_year"].replace(",", "")) < 8760


def test_a_campaign_profile_carries_its_months(book: str) -> None:
    added = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "profile",
        "add",
        "CAMP",
        "Beet campaign",
        "--pattern",
        "campaign",
        "--months",
        "9,10,11,12,1",
    )
    payload = json.loads(added.output)
    assert payload["months"] == "1,9,10,11,12"


def test_a_campaign_without_months_is_refused(book: str) -> None:
    result = run(book, "--site", "WRX1", "profile", "add", "CAMP", "Beet", "--pattern", "campaign")
    assert result.exit_code != 0


def test_a_load_factor_outside_the_range_is_refused(book: str) -> None:
    result = run(book, "--site", "WRX1", "profile", "add", "TRC", "Tracer", "--load-factor", "1.5")
    assert result.exit_code != 0


def test_an_empty_profile_list_says_so(book: str) -> None:
    assert "no profiles yet" in run(book, "--site", "WRX1", "profile", "list").output
