from __future__ import annotations

import sqlite3

import pytest

from dripleg.store.db import Database
from dripleg.store.migrations import migrate


@pytest.fixture
def book() -> Database:
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
    return db


def observation(book: Database, **overrides: object) -> None:
    row: dict[str, object] = {
        "site_code": "WRX1",
        "survey_reference": "S2025-1",
        "tag": "B12-MP-0043",
        "observed_on": "2025-04-08",
        "technician": "R Ellis",
        "reported_condition": "ok",
    }
    row.update(overrides)
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    book.execute(f"INSERT INTO observation ({columns}) VALUES ({marks})", list(row.values()))


def test_the_survey_tables_land(book: Database) -> None:
    for table in ("survey", "route", "route_stop", "observation"):
        assert book.has_table(table)


def test_a_survey_cannot_finish_before_it_starts(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO survey (site_code, reference, name, contractor, started_on, "
            "finished_on) VALUES (?, ?, ?, ?, ?, ?)",
            ("WRX1", "S2025-2", "Autumn", "Vane", "2025-10-01", "2025-09-01"),
        )


def test_an_observation_needs_a_survey(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        observation(book, survey_reference="NOPE")


def test_a_trap_is_read_once_per_survey(book: Database) -> None:
    observation(book)
    with pytest.raises(sqlite3.IntegrityError):
        observation(book)


def test_an_ultrasonic_level_needs_its_window(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        observation(book, ultrasonic_db=42.0)


def test_an_ultrasonic_pair_lands(book: Database) -> None:
    observation(book, ultrasonic_db=42.0, ultrasonic_seconds=30.0, ultrasonic_cycles=2)
    assert book.scalar("SELECT ultrasonic_cycles FROM observation") == 2


def test_a_level_off_the_meter_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        observation(book, ultrasonic_db=200.0, ultrasonic_seconds=30.0)


def test_one_side_of_a_temperature_pair_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        observation(book, upstream_f=340.0, temperature_method="contact_temperature")


def test_a_temperature_pair_needs_its_method(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        observation(book, upstream_f=340.0, downstream_f=210.0)


def test_a_full_temperature_reading_lands(book: Database) -> None:
    observation(
        book,
        upstream_f=340.0,
        downstream_f=210.0,
        ambient_f=72.0,
        temperature_method="contact_temperature",
    )
    assert book.scalar("SELECT downstream_f FROM observation") == 210.0


def test_closing_a_site_takes_its_surveys_and_readings(book: Database) -> None:
    observation(book)
    book.execute("DELETE FROM site WHERE code = 'WRX1'")
    assert book.scalar("SELECT COUNT(*) FROM survey") == 0
    assert book.scalar("SELECT COUNT(*) FROM observation") == 0


def test_a_route_stop_is_unique_by_position_and_by_tag(book: Database) -> None:
    book.execute(
        "INSERT INTO route (site_code, code, name) VALUES (?, ?, ?)", ("WRX1", "R1", "Ground floor")
    )
    book.execute(
        "INSERT INTO route_stop (site_code, route_code, position, tag) VALUES (?, ?, ?, ?)",
        ("WRX1", "R1", 0, "B12-MP-0001"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        book.execute(
            "INSERT INTO route_stop (site_code, route_code, position, tag) VALUES (?, ?, ?, ?)",
            ("WRX1", "R1", 0, "B12-MP-0002"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        book.execute(
            "INSERT INTO route_stop (site_code, route_code, position, tag) VALUES (?, ?, ?, ?)",
            ("WRX1", "R1", 1, "B12-MP-0001"),
        )


def test_a_stop_needs_a_route(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        book.execute(
            "INSERT INTO route_stop (site_code, route_code, position, tag) VALUES (?, ?, ?, ?)",
            ("WRX1", "R9", 0, "B12-MP-0001"),
        )


def test_dropping_a_route_takes_its_stops(book: Database) -> None:
    book.execute(
        "INSERT INTO route (site_code, code, name) VALUES (?, ?, ?)", ("WRX1", "R1", "Ground floor")
    )
    book.execute(
        "INSERT INTO route_stop (site_code, route_code, position, tag) VALUES (?, ?, ?, ?)",
        ("WRX1", "R1", 0, "B12-MP-0001"),
    )
    book.execute("DELETE FROM route WHERE site_code = 'WRX1' AND code = 'R1'")
    assert book.scalar("SELECT COUNT(*) FROM route_stop") == 0


def test_a_route_with_no_time_per_stop_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO route (site_code, code, name, minutes_per_stop) VALUES (?, ?, ?, ?)",
            ("WRX1", "R2", "Bad", 0.0),
        )
