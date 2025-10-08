"""Check the migration set before it reaches a plant's book.

Four things, and every one of them has gone wrong somewhere:

- the numbers run from one with no gaps, so `up_to` means what it looks like
- no two migrations share a number
- every migration's SQL parses into statements, so a missing semicolon is found
  here rather than halfway through applying it to a live book
- applying the whole set to an empty book produces the schema this build
  expects, which catches a migration that was edited after it was written

The last one is why the schema fingerprint is computed rather than stored: a
stored fingerprint has to be updated by hand and is therefore updated wrongly.
"""

from __future__ import annotations

import argparse
import hashlib
import sys

from dripleg.errors import DriplegError
from dripleg.store.db import Database, split_statements
from dripleg.store.migrations import MIGRATIONS, Migration, migrate

__all__ = ["Finding", "check", "main", "schema_fingerprint"]


class Finding(str):
    """A problem, as a string that can be printed straight out."""


def _numbering() -> list[Finding]:
    numbers = [m.number for m in MIGRATIONS]
    found: list[Finding] = []
    if len(set(numbers)) != len(numbers):
        found.append(Finding("two migrations share a number"))
    if numbers != sorted(numbers):
        found.append(Finding("the migrations are not in number order"))
    if numbers and numbers[0] != 1:
        found.append(Finding(f"the migrations start at {numbers[0]}, not 1"))
    for earlier, later in zip(numbers, numbers[1:], strict=False):
        if later != earlier + 1:
            found.append(Finding(f"there is a gap between migration {earlier} and {later}"))
    return found


def _parses(migration: Migration) -> list[Finding]:
    try:
        statements = list(split_statements(migration.sql))
    except DriplegError as problem:
        return [Finding(f"{migration} does not parse: {problem}")]
    if not statements:
        return [Finding(f"{migration} has no statements in it")]
    return []


def schema_fingerprint(book: Database) -> str:
    """A stable hash of every table and index the book carries."""

    rows = book.query(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    )
    joined = "\n".join(f"{row['type']} {row['name']} {row['sql']}" for row in rows)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _applies() -> tuple[list[Finding], str]:
    found: list[Finding] = []
    with Database() as book:
        try:
            applied = migrate(book)
        except Exception as problem:  # noqa: BLE001 - the point is to report anything
            return [Finding(f"the migrations do not apply to an empty book: {problem}")], ""
        if len(applied) != len(MIGRATIONS):
            found.append(Finding(f"{len(applied)} of {len(MIGRATIONS)} migrations applied"))
        if migrate(book):
            found.append(Finding("running the migrations twice applied something again"))
        return found, schema_fingerprint(book)


def check() -> tuple[list[Finding], str]:
    """Everything wrong with the migration set, and the schema it produces."""

    found = _numbering()
    for migration in MIGRATIONS:
        found.extend(_parses(migration))
    applied, fingerprint = _applies()
    found.extend(applied)
    return found, fingerprint


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the migration set.")
    parser.add_argument("--print-fingerprint", action="store_true")
    args = parser.parse_args(argv)
    problems, fingerprint = check()
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    if args.print_fingerprint:
        print(fingerprint)
    else:
        print(f"{len(MIGRATIONS)} migrations, schema {fingerprint[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
