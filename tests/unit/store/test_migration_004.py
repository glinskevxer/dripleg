from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from dripleg.store.db import Database
from dripleg.store.migrations import migrate


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    db.execute(
        "INSERT INTO site (code, name, operator, fuel_price_basis) VALUES (?, ?, ?, ?)",
        ("WRX1", "Mill", "Bryn", "gas"),
    )
    db.execute(
        "INSERT INTO survey (site_code, reference, name, contractor, started_on) "
        "VALUES (?, ?, ?, ?, ?)",
        ("WRX1", "S2025-1", "Spring", "Vane Energy", "2025-04-07"),
    )
    db.execute(
        "INSERT INTO observation (site_code, survey_reference, tag, observed_on, "
        "technician, reported_condition) VALUES (?, ?, ?, ?, ?, ?)",
        ("WRX1", "S2025-1", "B12-MP-0043", "2025-04-08", "R Ellis", "ok"),
    )
    yield db
    db.close()


def finding(book: Database, **overrides: object) -> None:
    row: dict[str, object] = {
        "site_code": "WRX1",
        "survey_reference": "S2025-1",
        "tag": "B12-MP-0043",
        "diagnosed": "blowing_through",
        "reported": "ok",
        "confidence": 0.8,
    }
    row.update(overrides)
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    book.execute(f"INSERT INTO finding ({columns}) VALUES ({marks})", list(row.values()))


def order(book: Database, **overrides: object) -> None:
    row: dict[str, object] = {
        "number": "WO-4411",
        "site_code": "WRX1",
        "tag": "B12-MP-0043",
        "action": "repair",
        "state": "raised",
        "raised_on": "2025-04-14",
        "due_on": "2025-05-14",
        "estimated_cost_cents": 13840,
    }
    row.update(overrides)
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    book.execute(f"INSERT INTO work_order ({columns}) VALUES ({marks})", list(row.values()))


def test_the_new_tables_land(book: Database) -> None:
    for table in ("finding", "work_order", "work_order_event"):
        assert book.has_table(table)


def test_a_finding_needs_the_reading_it_came_from(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        finding(book, tag="B12-MP-0099")


def test_a_good_finding_lands(book: Database) -> None:
    finding(book, pounds_per_hour=48.2, annual_cost_cents=261318)
    assert book.scalar("SELECT annual_cost_cents FROM finding") == 261318


def test_a_confidence_outside_zero_to_one_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        finding(book, confidence=1.4)


def test_a_negative_loss_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        finding(book, pounds_per_year=-1.0)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        finding(book, annual_cost_cents=-1)


def test_deleting_the_reading_takes_the_finding(book: Database) -> None:
    finding(book)
    book.execute("DELETE FROM observation")
    assert book.scalar("SELECT COUNT(*) FROM finding") == 0


def test_a_work_order_lands(book: Database) -> None:
    order(book)
    assert book.scalar("SELECT state FROM work_order") == "raised"


def test_a_work_order_number_is_unique(book: Database) -> None:
    order(book)
    with pytest.raises(sqlite3.IntegrityError):
        order(book)


def test_a_due_date_before_the_raised_date_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        order(book, due_on="2025-04-01")


def test_a_verified_order_has_to_carry_its_dates(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        order(book, state="verified")
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        order(book, state="verified", verified_on="2025-04-20")


def test_a_verified_order_with_both_dates_lands(book: Database) -> None:
    order(
        book,
        state="verified",
        completed_on="2025-04-18",
        verified_on="2025-04-20",
    )
    assert book.scalar("SELECT verified_on FROM work_order") == "2025-04-20"


def test_verification_cannot_predate_the_work(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        order(
            book,
            state="verified",
            completed_on="2025-04-20",
            verified_on="2025-04-18",
        )


def test_a_completion_before_the_raised_date_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        order(book, completed_on="2025-04-01")


def test_events_hang_off_an_order_and_go_with_it(book: Database) -> None:
    order(book)
    book.execute(
        "INSERT INTO work_order_event (number, position, note) VALUES (?, ?, ?)",
        ("WO-4411", 0, "raised to issued"),
    )
    book.execute("DELETE FROM work_order WHERE number = 'WO-4411'")
    assert book.scalar("SELECT COUNT(*) FROM work_order_event") == 0


def test_an_event_needs_an_order(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        book.execute(
            "INSERT INTO work_order_event (number, position, note) VALUES (?, ?, ?)",
            ("WO-9999", 0, "orphan"),
        )


def test_the_indexes_are_there(book: Database) -> None:
    names = {
        str(row["name"])
        for row in book.query("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert {"finding_by_cost", "finding_by_condition", "work_order_by_tag"} <= names
