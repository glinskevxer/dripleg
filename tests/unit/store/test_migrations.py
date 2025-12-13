from __future__ import annotations

import pytest

from dripleg.errors import ConflictError
from dripleg.store.db import Database
from dripleg.store.migrations import (
    MIGRATIONS,
    Migration,
    applied_migrations,
    migrate,
    schema_version,
)


def test_migration_numbers_are_unique_and_run_from_one() -> None:
    numbers = [m.number for m in MIGRATIONS]
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)
    assert numbers[0] == 1


def test_every_migration_has_a_name_and_some_sql() -> None:
    for migration in MIGRATIONS:
        assert migration.name.strip()
        assert any(word in migration.sql.upper() for word in ("CREATE", "ALTER", "DROP"))


def test_a_checksum_follows_the_sql() -> None:
    first = Migration(1, "a", "CREATE TABLE a (id INTEGER PRIMARY KEY)")
    same = Migration(1, "a", "  CREATE TABLE a (id INTEGER PRIMARY KEY)  ")
    other = Migration(1, "a", "CREATE TABLE b (id INTEGER PRIMARY KEY)")
    assert first.checksum == same.checksum
    assert first.checksum != other.checksum
    assert len(first.checksum) == 64


def test_a_fresh_book_is_at_version_zero() -> None:
    with Database() as book:
        assert schema_version(book) == 0
        assert applied_migrations(book) == {}


def test_migrating_applies_everything_once() -> None:
    with Database() as book:
        run = migrate(book)
        assert [m.number for m in run] == [m.number for m in MIGRATIONS]
        assert schema_version(book) == MIGRATIONS[-1].number
        assert migrate(book) == []


def test_the_tables_land() -> None:
    with Database() as book:
        migrate(book)
        for table in ("site", "area", "header", "schema_migration"):
            assert book.has_table(table)


def test_the_ledger_records_the_checksums() -> None:
    with Database() as book:
        migrate(book)
        recorded = applied_migrations(book)
        for migration in MIGRATIONS:
            assert recorded[migration.number] == migration.checksum


def test_migrating_up_to_a_number_stops_there() -> None:
    with Database() as book:
        run = migrate(book, up_to=1)
        assert [m.number for m in run] == [1]
        assert schema_version(book) == 1


def test_an_edited_migration_is_caught_on_the_next_open() -> None:
    with Database() as book:
        migrate(book)
        book.execute(
            "UPDATE schema_migration SET checksum = ? WHERE number = 1",
            ("0" * 64,),
        )
        with pytest.raises(ConflictError, match="has changed since this book applied it"):
            migrate(book)


def test_a_book_from_the_future_is_caught() -> None:
    with Database() as book:
        migrate(book)
        book.execute(
            "INSERT INTO schema_migration (number, name, checksum) VALUES (?, ?, ?)",
            (99, "something later", "f" * 64),
        )
        with pytest.raises(ConflictError, match="this build does not have it"):
            migrate(book)


def test_the_schema_holds_its_own_rules() -> None:
    with Database() as book:
        migrate(book)
        book.execute(
            "INSERT INTO site (code, name, operator, fuel_price_basis) VALUES (?, ?, ?, ?)",
            ("WRX1", "Mill", "Bryn", "gas"),
        )
        book.execute(
            "INSERT INTO area (site_code, code, name, cost_centre) VALUES (?, ?, ?, ?)",
            ("WRX1", "B12", "Machine", "CC1"),
        )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            book.execute(
                "INSERT INTO header (site_code, area_code, system_code, name, "
                "operating_psia, design_psia, discharge_psia, destination) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("WRX1", "B12", "MP", "Main", 139.7, 100.0, 29.7, "return"),
            )


def test_an_area_cannot_be_its_own_parent_in_the_schema_either() -> None:
    with Database() as book:
        migrate(book)
        book.execute(
            "INSERT INTO site (code, name, operator, fuel_price_basis) VALUES (?, ?, ?, ?)",
            ("WRX1", "Mill", "Bryn", "gas"),
        )
        with pytest.raises(Exception, match="CHECK constraint failed"):
            book.execute(
                "INSERT INTO area (site_code, code, name, cost_centre, parent_code) "
                "VALUES (?, ?, ?, ?, ?)",
                ("WRX1", "B12", "Machine", "CC1", "B12"),
            )


def test_deleting_a_site_takes_its_areas_with_it() -> None:
    with Database() as book:
        migrate(book)
        book.execute(
            "INSERT INTO site (code, name, operator, fuel_price_basis) VALUES (?, ?, ?, ?)",
            ("WRX1", "Mill", "Bryn", "gas"),
        )
        book.execute(
            "INSERT INTO area (site_code, code, name, cost_centre) VALUES (?, ?, ?, ?)",
            ("WRX1", "B12", "Machine", "CC1"),
        )
        book.execute("DELETE FROM site WHERE code = 'WRX1'")
        assert book.scalar("SELECT COUNT(*) FROM area") == 0


def test_printing_a_migration() -> None:
    assert str(MIGRATIONS[0]).startswith("001 ")
