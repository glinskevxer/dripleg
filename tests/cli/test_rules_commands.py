from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from dripleg.cli.main import cli

EXPORT = (
    "tag,date,by,condition,db,seconds,cycles,up_f,down_f,amb_f,glass,psig,note\n"
    "B12-MP-1,2025-04-08,R Ellis,pass,70,30,0,345,258,74,,,\n"
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
    run(
        target,
        "--site",
        "WRX1",
        "trap",
        "add",
        "B12-MP-1",
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


def test_every_rule_is_on_to_begin_with(book: str) -> None:
    payload = json.loads(run(book, "--site", "WRX1", "--json", "rules", "list").output)
    assert len(payload) >= 18
    assert all(row["state"] == "on" for row in payload)
    assert all(row["description"] for row in payload)


def test_a_rule_can_be_switched_off_with_a_reason(book: str) -> None:
    switched = run(
        book,
        "--site",
        "WRX1",
        "--json",
        "rules",
        "off",
        "TMP-1",
        "--reason",
        "our return line runs hot",
        "--on",
        "2025-04-14",
    )
    payload = json.loads(switched.output)
    assert payload["rule"] == "TMP-1"
    assert payload["state"] == "off"
    listed = json.loads(run(book, "--site", "WRX1", "--json", "rules", "list", "--off-only").output)
    assert len(listed) == 1
    assert listed[0]["rule"] == "TMP-1"
    assert listed[0]["reason"] == "our return line runs hot"


def test_switching_a_rule_off_changes_what_the_engine_runs(book: str) -> None:
    before = json.loads(run(book, "--site", "WRX1", "--json", "rules", "on", "TMP-1").output)[
        "rules_running"
    ]
    after = json.loads(
        run(
            book,
            "--site",
            "WRX1",
            "--json",
            "rules",
            "off",
            "TMP-1",
            "--reason",
            "not here",
        ).output
    )["rules_running"]
    assert after == before - 1


def test_a_switched_off_rule_stops_firing(book: str) -> None:
    before = json.loads(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1").output)
    run(
        book,
        "--site",
        "WRX1",
        "rules",
        "off",
        "COR-1",
        "--reason",
        "not trusted here",
    )
    run(book, "--site", "WRX1", "rules", "off", "SND-1", "--reason", "not trusted here")
    run(book, "--site", "WRX1", "rules", "off", "SND-5", "--reason", "not trusted here")
    run(book, "--site", "WRX1", "rules", "off", "TMP-1", "--reason", "not trusted here")
    after = json.loads(run(book, "--site", "WRX1", "--json", "loss", "report", "S2025-1").output)
    assert before["losing"] == 1
    assert after["losing"] == 0


def test_a_rule_can_be_switched_back_on(book: str) -> None:
    run(book, "--site", "WRX1", "rules", "off", "TMP-1", "--reason", "not here")
    switched = json.loads(run(book, "--site", "WRX1", "--json", "rules", "on", "TMP-1").output)
    assert switched["was_off"] is True
    assert (
        "every rule is on at this site"
        in run(book, "--site", "WRX1", "rules", "list", "--off-only").output
    )


def test_switching_on_a_rule_that_was_already_on(book: str) -> None:
    switched = json.loads(run(book, "--site", "WRX1", "--json", "rules", "on", "TMP-1").output)
    assert switched["was_off"] is False


def test_a_rule_this_build_does_not_have_cannot_be_switched_off(book: str) -> None:
    result = run(book, "--site", "WRX1", "rules", "off", "ZZZ-9", "--reason", "no")
    assert result.exit_code != 0


def test_a_reason_is_required(book: str) -> None:
    assert run(book, "--site", "WRX1", "rules", "off", "TMP-1").exit_code != 0


def test_nothing_is_stale_to_begin_with(book: str) -> None:
    assert (
        "every exclusion names a rule this build has"
        in run(book, "--site", "WRX1", "rules", "stale").output
    )


def test_an_exclusion_naming_a_gone_rule_shows_as_stale(book: str) -> None:
    import sqlite3

    run(book, "--site", "WRX1", "rules", "off", "TMP-1", "--reason", "not here")
    connection = sqlite3.connect(book)
    connection.execute("UPDATE rule_exclusion SET rule_code = 'GONE-1'")
    connection.commit()
    connection.close()
    payload = json.loads(run(book, "--site", "WRX1", "--json", "rules", "stale").output)
    assert payload[0]["rule"] == "GONE-1"
