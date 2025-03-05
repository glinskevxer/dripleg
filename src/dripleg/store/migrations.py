"""Numbered migrations, applied in order, with a checksum on what was applied.

There is no migration framework here on purpose. The whole schema is a few
hundred lines of SQL and the interesting behaviour is one rule: a migration
that has already run must not have changed since it ran. Editing an applied
migration is the way a schema quietly diverges between one plant's book and the
next, and the divergence is only found months later by a report that returns
nothing.

So each migration carries a sha256 of its own SQL, the book records the
checksum it applied, and a mismatch stops everything before the first read.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from dripleg.errors import ConflictError
from dripleg.store.db import Database

__all__ = ["MIGRATIONS", "Migration", "applied_migrations", "migrate", "schema_version"]

_LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migration (
    number      INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


@dataclass(frozen=True)
class Migration:
    number: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.strip().encode("utf-8")).hexdigest()

    def __str__(self) -> str:
        return f"{self.number:03d} {self.name}"


MIGRATION_001 = Migration(
    1,
    "sites areas and headers",
    """
    CREATE TABLE site (
        code                    TEXT PRIMARY KEY,
        name                    TEXT NOT NULL,
        operator                TEXT NOT NULL,
        programme_start_month   INTEGER NOT NULL DEFAULT 1,
        fuel_price_basis        TEXT NOT NULL,
        CHECK (programme_start_month BETWEEN 1 AND 12)
    );

    CREATE TABLE area (
        site_code   TEXT NOT NULL REFERENCES site(code) ON DELETE CASCADE,
        code        TEXT NOT NULL,
        name        TEXT NOT NULL,
        cost_centre TEXT NOT NULL,
        parent_code TEXT,
        PRIMARY KEY (site_code, code),
        CHECK (parent_code IS NULL OR parent_code <> code)
    );

    CREATE TABLE header (
        site_code           TEXT NOT NULL,
        area_code           TEXT NOT NULL,
        system_code         TEXT NOT NULL,
        name                TEXT NOT NULL,
        operating_psia      REAL NOT NULL,
        design_psia         REAL NOT NULL,
        discharge_psia      REAL NOT NULL,
        destination         TEXT NOT NULL,
        PRIMARY KEY (site_code, area_code, system_code),
        FOREIGN KEY (site_code, area_code) REFERENCES area(site_code, code) ON DELETE CASCADE,
        CHECK (operating_psia > 0),
        CHECK (design_psia >= operating_psia),
        CHECK (discharge_psia <= operating_psia)
    );

    CREATE INDEX header_by_area ON header (site_code, area_code);
    """,
)

MIGRATIONS: tuple[Migration, ...] = (MIGRATION_001,)


def schema_version(book: Database) -> int:
    """The highest migration number this book has applied, or zero."""

    if not book.has_table("schema_migration"):
        return 0
    return int(book.scalar("SELECT COALESCE(MAX(number), 0) FROM schema_migration") or 0)


def applied_migrations(book: Database) -> dict[int, str]:
    """Migration number to the checksum the book recorded for it."""

    if not book.has_table("schema_migration"):
        return {}
    rows = book.query("SELECT number, checksum FROM schema_migration ORDER BY number")
    return {int(row["number"]): str(row["checksum"]) for row in rows}


def _check_history(book: Database) -> None:
    known = {m.number: m for m in MIGRATIONS}
    for number, checksum in applied_migrations(book).items():
        migration = known.get(number)
        if migration is None:
            raise ConflictError(
                f"this book has migration {number:03d} applied and this build does not have it"
            )
        if migration.checksum != checksum:
            raise ConflictError(f"migration {migration} has changed since this book applied it")


def migrate(book: Database, *, up_to: int | None = None) -> list[Migration]:
    """Apply whatever is outstanding and return what was applied.

    Each migration lands in its own transaction together with its ledger row,
    so a failure halfway through a run leaves the book at the last migration
    that finished rather than somewhere between two.
    """

    book.execute(_LEDGER)
    _check_history(book)
    ceiling = up_to if up_to is not None else MIGRATIONS[-1].number
    done = set(applied_migrations(book))
    run: list[Migration] = []
    for migration in sorted(MIGRATIONS, key=lambda m: m.number):
        if migration.number in done or migration.number > ceiling:
            continue
        with book.transaction():
            book.execute_batch(migration.sql)
            book.execute(
                "INSERT INTO schema_migration (number, name, checksum) VALUES (?, ?, ?)",
                (migration.number, migration.name, migration.checksum),
            )
        run.append(migration)
    return run
