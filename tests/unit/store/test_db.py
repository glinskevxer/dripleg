from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dripleg.errors import ConflictError, DriplegError
from dripleg.store.db import Database, open_book


@pytest.fixture
def book() -> Database:
    db = Database()
    db.execute_script(
        """
        CREATE TABLE header (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE trap (
            id INTEGER PRIMARY KEY,
            tag TEXT NOT NULL UNIQUE,
            header_id INTEGER NOT NULL REFERENCES header(id)
        );
        """
    )
    return db


def test_a_fresh_book_has_foreign_keys_on(book: Database) -> None:
    assert book.foreign_keys_on


def test_an_orphan_row_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        book.execute("INSERT INTO trap (tag, header_id) VALUES ('B12-MP-1', 99)")


def test_rows_come_back_by_name(book: Database) -> None:
    book.execute("INSERT INTO header (name) VALUES ('MP main')")
    row = book.one("SELECT id, name FROM header")
    assert row is not None
    assert row["name"] == "MP main"


def test_scalar_reads_the_first_column(book: Database) -> None:
    book.execute("INSERT INTO header (name) VALUES ('MP main')")
    assert book.scalar("SELECT COUNT(*) FROM header") == 1
    assert book.scalar("SELECT name FROM header WHERE id = 99") is None


def test_execute_returns_the_new_row_id(book: Database) -> None:
    first = book.execute("INSERT INTO header (name) VALUES ('a')")
    second = book.execute("INSERT INTO header (name) VALUES ('b')")
    assert second == first + 1


def test_execute_many_writes_a_batch(book: Database) -> None:
    book.execute_many("INSERT INTO header (name) VALUES (?)", [("a",), ("b",), ("c",)])
    assert book.scalar("SELECT COUNT(*) FROM header") == 3


def test_a_transaction_that_finishes_lands(book: Database) -> None:
    with book.transaction():
        book.execute("INSERT INTO header (name) VALUES ('MP main')")
    assert book.scalar("SELECT COUNT(*) FROM header") == 1


def test_a_transaction_that_raises_leaves_nothing(book: Database) -> None:
    def half_a_write() -> None:
        with book.transaction():
            book.execute("INSERT INTO header (name) VALUES ('MP main')")
            raise RuntimeError("something went wrong halfway")

    with pytest.raises(RuntimeError, match="halfway"):
        half_a_write()
    assert book.scalar("SELECT COUNT(*) FROM header") == 0


def test_nesting_only_commits_at_the_outside(book: Database) -> None:
    seen: list[bool] = []
    with book.transaction():
        book.execute("INSERT INTO header (name) VALUES ('a')")
        with book.transaction():
            book.execute("INSERT INTO header (name) VALUES ('b')")
        seen.append(book.in_transaction)
    seen.append(book.in_transaction)
    assert seen == [True, False]
    assert book.scalar("SELECT COUNT(*) FROM header") == 2


def test_an_inner_failure_rolls_the_whole_thing_back(book: Database) -> None:
    def nested_write() -> None:
        with book.transaction():
            book.execute("INSERT INTO header (name) VALUES ('a')")
            with book.transaction():
                book.execute("INSERT INTO header (name) VALUES ('b')")
                raise ValueError("the inner one gave up")

    with pytest.raises(ValueError, match="inner one"):
        nested_write()
    assert book.scalar("SELECT COUNT(*) FROM header") == 0
    assert book.in_transaction is False


def test_the_book_lists_its_tables_and_columns(book: Database) -> None:
    assert book.table_names() == ["header", "trap"]
    assert book.has_table("trap")
    assert not book.has_table("survey")
    assert book.column_names("trap") == ["id", "tag", "header_id"]


def test_asking_about_a_table_that_is_not_there(book: Database) -> None:
    with pytest.raises(DriplegError, match="no table called"):
        book.column_names("survey")


def test_the_integrity_check_passes_on_a_good_book(book: Database) -> None:
    book.integrity_check()


def test_a_book_on_disk_makes_its_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "wrx1.sqlite3"
    with open_book(target) as db:
        assert not db.is_memory
        db.execute_script("CREATE TABLE a (id INTEGER PRIMARY KEY)")
        assert db.has_table("a")
    assert target.exists()


def test_a_book_on_disk_keeps_what_was_written(tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    with open_book(target) as db:
        db.execute_script("CREATE TABLE a (id INTEGER PRIMARY KEY, name TEXT)")
        with db.transaction():
            db.execute("INSERT INTO a (name) VALUES ('kept')")
    with open_book(target) as db:
        assert db.scalar("SELECT name FROM a") == "kept"


def test_an_in_memory_book_says_so() -> None:
    with Database() as db:
        assert db.is_memory
        assert repr(db) == "Database(':memory:')"


def test_a_corrupt_book_fails_its_check(tmp_path: Path) -> None:
    target = tmp_path / "broken.sqlite3"
    with open_book(target) as db:
        db.execute_script("CREATE TABLE a (id INTEGER PRIMARY KEY)")
    with target.open("r+b") as handle:
        handle.seek(4096)
        handle.write(b"\x00" * 512)
    db = open_book(target)
    with pytest.raises(ConflictError, match="integrity check"):
        db.integrity_check()
    db.close()


def test_a_script_splits_into_statements() -> None:
    from dripleg.store.db import split_statements

    parts = list(
        split_statements(
            """
            CREATE TABLE a (id INTEGER PRIMARY KEY);
            CREATE TABLE b (id INTEGER PRIMARY KEY);
            """
        )
    )
    assert len(parts) == 2
    assert parts[0].startswith("CREATE TABLE a")


def test_splitting_keeps_a_trigger_body_in_one_piece() -> None:
    from dripleg.store.db import split_statements

    parts = list(
        split_statements(
            """
            CREATE TABLE a (id INTEGER PRIMARY KEY, n INTEGER);
            CREATE TRIGGER bump AFTER INSERT ON a
            BEGIN
                UPDATE a SET n = n + 1 WHERE id = NEW.id;
            END;
            """
        )
    )
    assert len(parts) == 2
    assert "END" in parts[1]


def test_an_unfinished_statement_is_refused() -> None:
    from dripleg.store.db import split_statements

    with pytest.raises(DriplegError, match="unfinished statement"):
        list(split_statements("CREATE TABLE a (id INTEGER"))


def test_a_batch_runs_inside_an_open_transaction(book: Database) -> None:
    def half_a_schema() -> None:
        with book.transaction():
            book.execute_batch(
                "CREATE TABLE x (id INTEGER PRIMARY KEY);CREATE TABLE y (id INTEGER PRIMARY KEY);"
            )
            raise RuntimeError("changed my mind")

    with pytest.raises(RuntimeError, match="changed my mind"):
        half_a_schema()
    assert not book.has_table("x")
    assert not book.has_table("y")
