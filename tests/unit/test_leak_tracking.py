from __future__ import annotations

from dripleg.store.db import Database
from tests.support import leaks


def test_a_closed_book_leaves_nothing_behind() -> None:
    before = leaks.TRACKER.open_count
    book = Database()
    assert leaks.TRACKER.open_count == before + 1
    book.close()
    assert leaks.TRACKER.open_count == before


def test_a_context_managed_book_closes_itself() -> None:
    before = leaks.TRACKER.open_count
    with Database() as book:
        assert book.is_memory
    assert leaks.TRACKER.open_count == before


def test_the_tracker_names_the_test_that_leaked() -> None:
    leaks.TRACKER.working_on("some other test")
    book = Database()
    leaks.TRACKER.working_on("this test")
    found = leaks.TRACKER.leaked_here("some other test")
    assert len(found) == 1
    assert "never closed" in found[0]
    book.close()


def test_forgetting_a_label_clears_it() -> None:
    leaks.TRACKER.working_on("a doomed test")
    book = Database()
    leaks.TRACKER.working_on("this test")
    leaks.TRACKER.forget("a doomed test")
    assert leaks.TRACKER.leaked_here("a doomed test") == []
    book.close()


def test_installing_twice_does_not_wrap_twice() -> None:
    leaks.install()
    leaks.install()
    before = leaks.TRACKER.open_count
    book = Database()
    assert leaks.TRACKER.open_count == before + 1
    book.close()
    assert leaks.TRACKER.open_count == before
