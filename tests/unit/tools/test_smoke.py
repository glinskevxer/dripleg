from __future__ import annotations

import pytest

from dripleg.tools.smoke import build_plant, main, walk


def test_the_smoke_plant_is_two_traps_on_one_header() -> None:
    register, catalogue = build_plant()
    assert len(register) == 2
    assert len(catalogue) == 1
    assert len({s.header.key for s in register}) == 1


def test_the_walk_finds_the_blowing_trap() -> None:
    facts = walk()
    assert facts["traps"] == 2
    assert facts["failures"] == 1
    assert facts["losing"] == 1
    assert facts["jobs"] == 1


def test_the_walk_costs_the_blowing_trap() -> None:
    facts = walk()
    assert str(facts["annual_cost"]).startswith("$")
    assert str(facts["annual_cost"]) != "$0.00"


def test_the_walk_builds_the_schema() -> None:
    facts = walk()
    assert isinstance(facts["tables"], int)
    assert facts["tables"] >= 15


def test_the_walk_produces_a_report() -> None:
    assert int(str(walk()["report_lines"])) > 10


def test_the_walk_is_repeatable() -> None:
    assert walk() == walk()


def test_the_command_passes_and_prints(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "traps: 2" in out
    assert "annual cost: $" in out


def test_the_command_can_be_quiet(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--quiet"]) == 0
    assert capsys.readouterr().out == ""


def test_the_smoke_test_leaves_no_book_open() -> None:
    from tests.support import leaks

    before = leaks.TRACKER.open_count
    walk()
    assert leaks.TRACKER.open_count == before
