from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.support.cli import add_traps, make_book, run


@pytest.fixture
def book(tmp_path: Path) -> str:
    target = make_book(tmp_path)
    add_traps(target, ["B12-MP-1", "B12-MP-2"])
    return target


def test_a_book_with_only_notes_on_it_still_passes(book: str) -> None:
    result = run(book, "doctor", "--on", "2026-01-01")
    assert result.exit_code == 0
    assert "no routes" in result.output


def test_a_site_with_no_routes_gets_a_note(book: str) -> None:
    payload = json.loads(run(book, "--json", "doctor", "--on", "2026-01-01").output)
    assert [row["check"] for row in payload] == ["no routes"]
    assert payload[0]["severity"] == "note"


def test_a_note_alone_does_not_fail_the_command(book: str) -> None:
    assert run(book, "doctor", "--on", "2026-01-01").exit_code == 0


def test_partly_routed_traps_get_a_different_note(book: str) -> None:
    run(book, "route", "add", "R1", "Ground floor")
    run(book, "route", "stop", "R1", "B12-MP-1")
    payload = json.loads(run(book, "--json", "doctor", "--on", "2026-01-01").output)
    checks = [row["check"] for row in payload]
    assert "traps on no route" in checks
    assert "no routes" not in checks


def test_a_fully_routed_site_gets_no_route_note(book: str) -> None:
    run(book, "route", "add", "R1", "Ground floor")
    for tag in ("B12-MP-1", "B12-MP-2"):
        run(book, "route", "stop", "R1", tag)
    payload = json.loads(run(book, "--json", "doctor", "--on", "2026-01-01").output)
    assert payload == []


def test_an_audit_finding_is_an_error_and_fails_the_command(book: str) -> None:
    run(book, "route", "add", "R1", "Ground floor")
    run(book, "route", "stop", "R1", "B12-MP-9")
    result = run(book, "--json", "doctor", "--on", "2026-01-01")
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload[0]["severity"] == "error"
    assert payload[0]["check"] == "route stop on an unknown tag"


def test_an_expired_acceptance_is_a_warning(book: str) -> None:
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "3",
    )
    payload = json.loads(run(book, "--json", "doctor", "--on", "2026-01-01").output)
    warnings = [row for row in payload if row["severity"] == "warning"]
    assert warnings[0]["check"] == "accepted risk due for review"


def test_a_live_acceptance_is_not_a_warning(book: str) -> None:
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "24",
    )
    payload = json.loads(run(book, "--json", "doctor", "--on", "2026-01-01").output)
    assert all(row["severity"] != "warning" for row in payload)


def test_a_warning_alone_passes_unless_strict(book: str) -> None:
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "3",
    )
    assert run(book, "doctor", "--on", "2026-01-01").exit_code == 0
    assert run(book, "doctor", "--on", "2026-01-01", "--strict").exit_code == 1


def test_a_stale_rule_exclusion_is_a_warning(book: str) -> None:
    run(book, "rules", "off", "TMP-1", "--reason", "not here")
    connection = sqlite3.connect(book)
    connection.execute("UPDATE rule_exclusion SET rule_code = 'GONE-1'")
    connection.commit()
    connection.close()
    payload = json.loads(run(book, "--json", "doctor", "--on", "2026-01-01").output)
    checks = [row["check"] for row in payload]
    assert "stale rule exclusion" in checks


def test_the_errors_come_before_the_warnings(book: str) -> None:
    run(book, "route", "add", "R1", "Ground floor")
    run(book, "route", "stop", "R1", "B12-MP-9")
    run(
        book,
        "risk",
        "accept",
        "B12-MP-1",
        "--reason",
        "not now",
        "--by",
        "H Weir",
        "--on",
        "2025-04-14",
        "--months",
        "3",
    )
    payload = json.loads(run(book, "--json", "doctor", "--on", "2026-01-01").output)
    severities = [row["severity"] for row in payload]
    assert severities == sorted(severities, key=lambda s: ("error", "warning", "note").index(s))


def test_a_book_that_is_not_there(tmp_path: Path) -> None:
    assert run(str(tmp_path / "nope.sqlite3"), "doctor").exit_code != 0
