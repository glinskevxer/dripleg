"""What every command needs: a book, opened once, and where it came from.

Click passes this down through `ctx.obj`. The book is opened lazily, because
`dripleg --help` and `dripleg version` have no business touching a file, and a
typo in a path should not create an empty sqlite database in the current
directory as a side effect of asking for help.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dripleg.errors import ConfigError
from dripleg.store.db import IN_MEMORY, Database, open_book
from dripleg.store.migrations import migrate, schema_version

__all__ = ["Context"]

DEFAULT_BOOK = "dripleg.sqlite3"


@dataclass
class Context:
    """The one object every command gets handed."""

    book_path: str = DEFAULT_BOOK
    site_code: str | None = None
    as_json: bool = False
    _book: Database | None = field(default=None, repr=False)

    @property
    def book(self) -> Database:
        if self._book is None:
            if self.book_path != IN_MEMORY and not Path(self.book_path).exists():
                raise ConfigError(
                    f"there is no book at {self.book_path}, run 'dripleg init' to make one"
                )
            self._book = open_book(self.book_path)
        return self._book

    def create_book(self) -> list[str]:
        """Make the book if it is not there and bring it up to date."""

        if self._book is None:
            self._book = open_book(self.book_path)
        applied = migrate(self._book)
        return [str(m) for m in applied]

    @property
    def version_of_book(self) -> int:
        return schema_version(self.book)

    def site(self) -> str:
        if self.site_code is None:
            raise ConfigError("say which site with --site")
        return self.site_code

    def close(self) -> None:
        if self._book is not None:
            self._book.close()
            self._book = None
