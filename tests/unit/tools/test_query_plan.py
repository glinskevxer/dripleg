from __future__ import annotations

import pytest

from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.tools.query_plan import HOT_QUERIES, HotQuery, check, explain, main


def test_every_hot_query_in_this_build_uses_an_index() -> None:
    assert check() == []


def test_every_hot_query_names_a_table_it_must_not_scan() -> None:
    with Database() as book:
        migrate(book)
        tables = set(book.table_names())
    for query in HOT_QUERIES:
        assert query.must_not_scan in tables
        assert query.name.strip()


def test_a_plan_comes_back_as_lines() -> None:
    with Database() as book:
        migrate(book)
        plan = explain(book, HOT_QUERIES[0])
    assert plan
    assert any("SEARCH" in line for line in plan)


def test_a_query_with_no_index_is_caught() -> None:
    query = HotQuery(
        name="a query nobody indexed",
        sql="SELECT * FROM observation WHERE technician = ?",
        parameters=("R Ellis",),
        must_not_scan="observation",
    )
    with Database() as book:
        migrate(book)
        plan = explain(book, query)
    assert any(line.startswith("SCAN") for line in plan)


def test_the_gate_passes_on_this_build(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert f"{len(HOT_QUERIES)} hot queries" in capsys.readouterr().out


def test_the_gate_can_print_the_plans(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--show"]) == 0
    out = capsys.readouterr().out
    assert "load the register for a site" in out
    assert "USING INDEX" in out


def test_printing_a_hot_query() -> None:
    assert str(HOT_QUERIES[0]).endswith("(must not scan trap_station)")


def test_the_register_load_uses_the_header_index() -> None:
    with Database() as book:
        migrate(book)
        plan = explain(book, HOT_QUERIES[0])
    assert any("station_by_header" in line for line in plan)


def test_the_findings_query_uses_the_cost_index() -> None:
    with Database() as book:
        migrate(book)
        query = next(q for q in HOT_QUERIES if "dearest" in q.name)
        plan = explain(book, query)
    assert any("finding_by_cost" in line for line in plan)
