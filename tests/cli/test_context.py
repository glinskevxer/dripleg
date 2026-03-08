from __future__ import annotations

from pathlib import Path

import pytest

from dripleg.cli.context import Context
from dripleg.errors import ConfigError
from dripleg.store.db import IN_MEMORY


def test_a_context_does_not_open_anything_until_it_is_asked(tmp_path: Path) -> None:
    target = tmp_path / "wrx1.sqlite3"
    context = Context(book_path=str(target))
    assert not target.exists()
    context.close()


def test_opening_a_book_that_is_not_there_says_what_to_do(tmp_path: Path) -> None:
    context = Context(book_path=str(tmp_path / "missing.sqlite3"))
    with pytest.raises(ConfigError, match="dripleg init"):
        _ = context.book


def test_creating_the_book_applies_the_migrations(tmp_path: Path) -> None:
    context = Context(book_path=str(tmp_path / "wrx1.sqlite3"))
    applied = context.create_book()
    assert applied
    assert context.version_of_book > 0
    context.close()


def test_creating_twice_is_quiet(tmp_path: Path) -> None:
    context = Context(book_path=str(tmp_path / "wrx1.sqlite3"))
    context.create_book()
    assert context.create_book() == []
    context.close()


def test_an_in_memory_book_needs_no_file() -> None:
    context = Context(book_path=IN_MEMORY)
    context.create_book()
    assert context.version_of_book > 0
    context.close()


def test_asking_for_the_site_on_a_book_with_no_schema() -> None:
    context = Context(book_path=IN_MEMORY)
    with pytest.raises(ConfigError, match="no sites on it yet"):
        context.site()
    context.site_code = "WRX1"
    assert context.site() == "WRX1"
    context.close()


def test_closing_twice_is_fine() -> None:
    context = Context(book_path=IN_MEMORY)
    context.create_book()
    context.close()
    context.close()


def _book_with(tmp_path: Path, codes: list[str]) -> Context:
    context = Context(book_path=str(tmp_path / "wrx1.sqlite3"))
    context.create_book()
    for code in codes:
        context.book.execute(
            "INSERT INTO site (code, name, operator, fuel_price_basis) VALUES (?, ?, ?, ?)",
            (code, f"Plant {code}", "Bryn", "gas"),
        )
    return context


def test_one_site_on_the_book_needs_no_option(tmp_path: Path) -> None:
    context = _book_with(tmp_path, ["WRX1"])
    assert context.site() == "WRX1"
    context.close()


def test_two_sites_on_the_book_have_to_be_told_apart(tmp_path: Path) -> None:
    context = _book_with(tmp_path, ["WRX1", "WRX2"])
    with pytest.raises(ConfigError, match="this book holds WRX1, WRX2"):
        context.site()
    context.close()


def test_an_option_beats_the_fallback(tmp_path: Path) -> None:
    context = _book_with(tmp_path, ["WRX1", "WRX2"])
    context.site_code = "WRX2"
    assert context.site() == "WRX2"
    context.close()


def test_an_empty_book_says_to_add_a_site(tmp_path: Path) -> None:
    context = _book_with(tmp_path, [])
    with pytest.raises(ConfigError, match="no sites on it yet"):
        context.site()
    context.close()


def test_the_site_codes_come_back_in_order(tmp_path: Path) -> None:
    context = _book_with(tmp_path, ["WRX2", "WRX1"])
    assert context.site_codes() == ["WRX1", "WRX2"]
    context.close()


def test_a_book_with_no_schema_lists_no_sites() -> None:
    context = Context(book_path=IN_MEMORY)
    assert context.site_codes() == []
    context.close()
