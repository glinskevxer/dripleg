"""Fail any test that walks away from an open sqlite connection.

Every `Database` this suite opens should be closed by the test that opened it.
An unclosed one on an in memory book is harmless in itself, and on a file book
under a temporary directory it holds the file open, which is why a Windows
checkout of an earlier version of this suite could not clean up after itself.

More usefully, a leak is a signal about the code rather than the test: a
repository that opens its own connection somewhere and does not close it will
show up here first.
"""

from __future__ import annotations

from dripleg.store.db import Database

__all__ = ["TRACKER", "Tracker", "install"]


class Tracker:
    """Which test opened which connection, and which are still open."""

    def __init__(self) -> None:
        self._open: dict[int, tuple[str, str]] = {}
        self._label = "collection"

    def working_on(self, label: str) -> None:
        self._label = label

    def opened(self, database: Database) -> None:
        self._open[id(database)] = (self._label, database.path)

    def closed(self, database: Database) -> None:
        self._open.pop(id(database), None)

    def leaked_here(self, label: str) -> list[str]:
        return [
            f"{path} was opened by {owner} and never closed"
            for owner, path in self._open.values()
            if owner == label
        ]

    def forget(self, label: str) -> None:
        for key, (owner, _) in list(self._open.items()):
            if owner == label:
                del self._open[key]

    @property
    def open_count(self) -> int:
        return len(self._open)


TRACKER = Tracker()
_installed = False


def install() -> None:
    """Wrap the database constructor once, however many times this is called."""

    global _installed
    if _installed:
        return
    original_init = Database.__init__
    original_close = Database.close

    def tracked_init(self: Database, path: object = ":memory:") -> None:
        original_init(self, path)  # type: ignore[arg-type]
        TRACKER.opened(self)

    def tracked_close(self: Database) -> None:
        original_close(self)
        TRACKER.closed(self)

    Database.__init__ = tracked_init  # type: ignore[method-assign]
    Database.close = tracked_close  # type: ignore[method-assign]
    _installed = True
