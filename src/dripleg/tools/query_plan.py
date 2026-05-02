"""Check the queries this package runs actually use the indexes it ships.

An index is written once and then quietly stops being used, usually because a
column got added to a WHERE clause or a query got rewritten with a join. The
suite still passes, because a full table scan on a hundred rows is instant, and
the plant with four thousand traps and eleven years of surveys finds out
instead.

So the hot queries are listed here with the table they must not scan, and this
runs `EXPLAIN QUERY PLAN` over an empty but migrated book and reads the answer.
Empty is fine: the plan sqlite picks does not depend on the data being there,
only on the schema and the indexes.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from dripleg.store.db import Database
from dripleg.store.migrations import migrate

__all__ = ["HOT_QUERIES", "HotQuery", "check", "explain", "main"]


@dataclass(frozen=True)
class HotQuery:
    """One query this package runs often, and the table it must not scan."""

    name: str
    sql: str
    parameters: tuple[object, ...]
    must_not_scan: str

    def __str__(self) -> str:
        return f"{self.name} (must not scan {self.must_not_scan})"


HOT_QUERIES: tuple[HotQuery, ...] = (
    HotQuery(
        name="load the register for a site",
        sql=(
            "SELECT * FROM trap_station WHERE site_code = ? "
            "ORDER BY area_code, system_code, sequence"
        ),
        parameters=("WRX1",),
        must_not_scan="trap_station",
    ),
    HotQuery(
        name="one trap's readings across every survey",
        sql="SELECT * FROM observation WHERE site_code = ? AND tag = ? ORDER BY observed_on",
        parameters=("WRX1", "B12-MP-0043"),
        must_not_scan="observation",
    ),
    HotQuery(
        name="the dearest findings at a site",
        sql=(
            "SELECT * FROM finding WHERE site_code = ? AND annual_cost_cents > 0 "
            "ORDER BY annual_cost_cents DESC, tag LIMIT 10"
        ),
        parameters=("WRX1",),
        must_not_scan="finding",
    ),
    HotQuery(
        name="the open work orders at a site",
        sql=(
            "SELECT number FROM work_order WHERE site_code = ? "
            "AND state NOT IN ('verified', 'cancelled') ORDER BY due_on, number"
        ),
        parameters=("WRX1",),
        must_not_scan="work_order",
    ),
    HotQuery(
        name="every order raised against one trap",
        sql="SELECT number FROM work_order WHERE site_code = ? AND tag = ? ORDER BY raised_on",
        parameters=("WRX1", "B12-MP-0043"),
        must_not_scan="work_order",
    ),
    HotQuery(
        name="the stations on one header",
        sql=(
            "SELECT * FROM trap_station WHERE site_code = ? AND area_code = ? AND system_code = ?"
        ),
        parameters=("WRX1", "B12", "MP"),
        must_not_scan="trap_station",
    ),
)


def explain(book: Database, query: HotQuery) -> list[str]:
    """The plan sqlite would use, one line per step."""

    rows = book.query(f"EXPLAIN QUERY PLAN {query.sql}", list(query.parameters))
    return [str(row["detail"]) for row in rows]


def check() -> list[str]:
    """Every hot query that would scan the table it must not."""

    problems: list[str] = []
    with Database() as book:
        migrate(book)
        for query in HOT_QUERIES:
            plan = explain(book, query)
            scanning = [
                step for step in plan if step.startswith("SCAN") and query.must_not_scan in step
            ]
            if scanning:
                problems.append(f"{query.name}: {scanning[0]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the hot queries use an index.")
    parser.add_argument("--show", action="store_true", help="Print every plan.")
    args = parser.parse_args(argv)
    if args.show:
        with Database() as book:
            migrate(book)
            for query in HOT_QUERIES:
                print(query.name)
                for step in explain(book, query):
                    print(f"  {step}")
    problems = check()
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"{len(HOT_QUERIES)} hot queries, none of them scanning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
