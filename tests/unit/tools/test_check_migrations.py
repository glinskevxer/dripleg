from __future__ import annotations

import pytest

from dripleg.store.db import Database
from dripleg.store.migrations import MIGRATIONS, migrate
from dripleg.tools.check_migrations import check, main, schema_fingerprint


def test_the_migration_set_in_this_build_is_clean() -> None:
    problems, fingerprint = check()
    assert problems == []
    assert len(fingerprint) == 64


def test_the_numbers_run_from_one_with_no_gaps() -> None:
    numbers = [m.number for m in MIGRATIONS]
    assert numbers == list(range(1, len(numbers) + 1))


def test_every_migration_parses_into_statements() -> None:
    from dripleg.store.db import split_statements

    for migration in MIGRATIONS:
        assert list(split_statements(migration.sql))


def test_the_fingerprint_follows_the_schema() -> None:
    with Database() as first, Database() as second:
        migrate(first)
        migrate(second)
        assert schema_fingerprint(first) == schema_fingerprint(second)
        second.execute("CREATE TABLE extra (id INTEGER PRIMARY KEY)")
        assert schema_fingerprint(first) != schema_fingerprint(second)


def test_an_empty_book_fingerprints_to_something_else() -> None:
    with Database() as empty, Database() as migrated:
        migrate(migrated)
        assert schema_fingerprint(empty) != schema_fingerprint(migrated)


def test_the_gate_passes_and_prints_the_count(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert f"{len(MIGRATIONS)} migrations" in out
    assert "schema " in out


def test_the_gate_can_print_just_the_fingerprint(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--print-fingerprint"]) == 0
    printed = capsys.readouterr().out.strip()
    assert len(printed) == 64


def test_the_fingerprint_matches_the_one_the_gate_computes() -> None:
    _, fingerprint = check()
    with Database() as book:
        migrate(book)
        assert schema_fingerprint(book) == fingerprint


def test_running_the_migrations_twice_applies_nothing() -> None:
    with Database() as book:
        assert len(migrate(book)) == len(MIGRATIONS)
        assert migrate(book) == []


def test_every_table_the_package_uses_is_in_the_schema() -> None:
    with Database() as book:
        migrate(book)
        tables = set(book.table_names())
    for name in (
        "site",
        "area",
        "header",
        "trap_model",
        "operating_profile",
        "trap_station",
        "survey",
        "route",
        "route_stop",
        "observation",
        "finding",
        "work_order",
        "work_order_event",
        "cost_basis",
        "schema_migration",
    ):
        assert name in tables
