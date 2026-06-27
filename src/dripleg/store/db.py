"""One sqlite file, opened the same way every time.

Everything here exists because sqlite's defaults are wrong for a book of record.
Foreign keys are off unless you turn them on per connection, which quietly
lets an orphan row in. Autocommit means a half written survey stays half
written. And the default row factory hands back tuples, so a column added in
the middle of a select breaks the caller silently rather than loudly.

So: one class, foreign keys on, rows by name, and writes only inside a
transaction that either lands or does not.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dripleg.errors import ConflictError, DriplegError

__all__ = ["Database", "open_book", "split_statements"]

IN_MEMORY = ":memory:"


class Database:
    """A connection to one book, with the settings this package needs."""

    def __init__(self, path: str | Path = IN_MEMORY) -> None:
        self.path = str(path)
        self._connection = sqlite3.connect(
            self.path,
            isolation_level=None,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._connection.row_factory = sqlite3.Row
        self._depth = 0
        self._statements = 0
        self._apply_settings()

    def _apply_settings(self) -> None:
        cursor = self._connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(
                "PRAGMA journal_mode = WAL"
                if not self.is_memory
                else "PRAGMA journal_mode = MEMORY"
            )
            cursor.execute("PRAGMA synchronous = FULL")
            cursor.execute("PRAGMA busy_timeout = 5000")
        finally:
            cursor.close()

    @property
    def statements(self) -> int:
        """How many statements this connection has run.

        Kept because the only way to catch a query per row creeping back into a
        bulk path is to count, and the only way to count reliably is here.
        """

        return self._statements

    def reset_statement_count(self) -> None:
        self._statements = 0

    @property
    def is_memory(self) -> bool:
        return self.path == IN_MEMORY

    @property
    def foreign_keys_on(self) -> bool:
        return bool(self.scalar("PRAGMA foreign_keys"))

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # Reading --------------------------------------------------------------

    def query(self, sql: str, parameters: Sequence[Any] = ()) -> list[sqlite3.Row]:
        self._statements += 1
        cursor = self._connection.execute(sql, parameters)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    def one(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Row | None:
        self._statements += 1
        cursor = self._connection.execute(sql, parameters)
        try:
            row: sqlite3.Row | None = cursor.fetchone()
            return row
        finally:
            cursor.close()

    def scalar(self, sql: str, parameters: Sequence[Any] = ()) -> Any:
        row = self.one(sql, parameters)
        return None if row is None else row[0]

    # Writing --------------------------------------------------------------

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> int:
        """Run one statement. Returns the row id where sqlite gives one."""

        self._statements += 1
        cursor = self._connection.execute(sql, parameters)
        try:
            return int(cursor.lastrowid or 0)
        finally:
            cursor.close()

    def execute_many(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        """One statement, however many rows go through it."""

        self._statements += 1
        cursor = self._connection.executemany(sql, rows)
        cursor.close()

    def execute_script(self, sql: str) -> None:
        """Run a whole script. Commits first, so never inside a transaction."""

        self._connection.executescript(sql)

    def execute_batch(self, sql: str) -> int:
        """Run several statements one at a time, inside whatever is open.

        `executescript` issues a COMMIT before it starts, which quietly ends
        any transaction the caller had open and leaves the rest of that unit of
        work outside it. A migration has to land together with its ledger row,
        so it comes through here instead: split on complete statements and
        execute them separately.
        """

        statements = list(split_statements(sql))
        for statement in statements:
            self._connection.execute(statement)
        return len(statements)

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        """Everything inside lands together or not at all.

        Nesting is allowed and only the outermost one commits, because a
        repository method that opens a transaction has to be callable from
        inside a bigger one without ending it early.
        """

        outermost = self._depth == 0
        if outermost:
            self._connection.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield self
        except Exception:
            self._depth -= 1
            if self._depth == 0:
                self._connection.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self._connection.execute("COMMIT")

    @property
    def in_transaction(self) -> bool:
        return self._depth > 0

    # Housekeeping ---------------------------------------------------------

    def table_names(self) -> list[str]:
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [str(row["name"]) for row in rows]

    def has_table(self, name: str) -> bool:
        return name in self.table_names()

    def column_names(self, table: str) -> list[str]:
        if not self.has_table(table):
            raise DriplegError(f"there is no table called {table!r}")
        return [str(row["name"]) for row in self.query(f"PRAGMA table_info({table})")]

    def integrity_check(self) -> None:
        """Ask sqlite whether the file is still a database.

        A badly damaged file raises rather than answering, so both endings
        arrive here as the same error and a caller does not have to know which
        kind of broken it got.
        """

        try:
            result = self.scalar("PRAGMA integrity_check")
        except sqlite3.DatabaseError as problem:
            raise ConflictError(f"the book failed its integrity check: {problem}") from problem
        if result != "ok":
            raise ConflictError(f"the book failed its integrity check: {result}")

    def __repr__(self) -> str:
        return f"Database({self.path!r})"


def split_statements(sql: str) -> Iterator[str]:
    """Cut a script into statements, using sqlite's own idea of complete.

    Splitting on semicolons is wrong the moment a trigger body turns up, and
    `sqlite3.complete_statement` is the same parser the shell uses to decide
    whether to keep prompting.
    """

    pending: list[str] = []
    for character in sql:
        pending.append(character)
        if character != ";":
            continue
        buffer = "".join(pending)
        if not sqlite3.complete_statement(buffer):
            continue
        statement = buffer.strip()
        if statement and statement != ";":
            yield statement
        pending.clear()
    leftover = "".join(pending).strip()
    if leftover:
        raise DriplegError(f"the script ends in an unfinished statement: {leftover[:60]!r}")


def open_book(path: str | Path = IN_MEMORY) -> Database:
    """Open a book, making the directory above it if it is not there."""

    if str(path) != IN_MEMORY:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return Database(path)
