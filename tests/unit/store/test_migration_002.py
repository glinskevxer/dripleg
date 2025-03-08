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
        "INSERT INTO area (site_code, code, name, cost_centre) VALUES (?, ?, ?, ?)",
        ("WRX1", "B12", "Machine", "CC1"),
    )
    db.execute(
        "INSERT INTO header (site_code, area_code, system_code, name, operating_psia, "
        "design_psia, discharge_psia, destination) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("WRX1", "B12", "MP", "Main", 139.7, 170.0, 29.7, "return"),
    )
    db.execute(
        "INSERT INTO operating_profile (site_code, code, name, pattern) VALUES (?, ?, ?, ?)",
        ("WRX1", "CONT", "Continuous", "continuous"),
    )
    db.execute(
        "INSERT INTO trap_model (manufacturer, code, principle, orifice_diameter_in, "
        "max_operating_psia, max_back_pressure_pct, connection_size_in, connection_type, "
        "list_price_cents) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("HALDEN", "TD52", "thermodynamic_disc", 0.093, 614.7, 80.0, 0.5, "screwed", 18400),
    )
    return db


def station(book: Database, **overrides: object) -> int:
    row: dict[str, object] = {
        "site_code": "WRX1",
        "tag": "B12-MP-0043",
        "area_code": "B12",
        "system_code": "MP",
        "sequence": 43,
        "model_manufacturer": "HALDEN",
        "model_code": "TD52",
        "service": "drip",
        "accessibility": "ground_level",
        "criticality": "nuisance",
        "profile_code": "CONT",
        "installed_on": "2021-06-14",
    }
    row.update(overrides)
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    return book.execute(
        f"INSERT INTO trap_station ({columns}) VALUES ({marks})", list(row.values())
    )


def test_the_new_tables_land(book: Database) -> None:
    for table in ("trap_model", "operating_profile", "trap_station"):
        assert book.has_table(table)


def test_a_station_needs_a_header_that_exists(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        station(book, system_code="HP")


def test_a_station_needs_a_model_that_exists(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        station(book, model_code="NOPE")


def test_a_station_needs_a_profile_that_exists(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        station(book, profile_code="NOPE")


def test_a_good_station_lands(book: Database) -> None:
    station(book)
    assert book.scalar("SELECT COUNT(*) FROM trap_station") == 1


def test_a_tag_is_unique_within_a_site(book: Database) -> None:
    station(book)
    with pytest.raises(sqlite3.IntegrityError):
        station(book)


def test_a_removal_date_before_the_install_date_is_refused(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        station(book, removed_on="2020-01-01")


def test_the_isolation_valve_count_is_bounded(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        station(book, isolation_valves=3)


def test_an_interval_override_is_bounded(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        station(book, interval_months_override=0)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        station(book, tag="B12-MP-0044", sequence=44, interval_months_override=61)


def test_only_a_discontinued_model_names_a_replacement(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO trap_model (manufacturer, code, principle, orifice_diameter_in, "
            "max_operating_psia, max_back_pressure_pct, connection_size_in, connection_type, "
            "list_price_cents, discontinued, replaced_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "HALDEN",
                "TD60",
                "thermodynamic_disc",
                0.093,
                614.7,
                80.0,
                0.5,
                "screwed",
                9000,
                0,
                "TD75",
            ),
        )


def test_a_campaign_profile_has_to_carry_months(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO operating_profile (site_code, code, name, pattern) VALUES (?, ?, ?, ?)",
            ("WRX1", "CAMP", "Beet campaign", "campaign"),
        )


def test_a_continuous_profile_cannot_carry_months(book: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        book.execute(
            "INSERT INTO operating_profile (site_code, code, name, pattern, campaign_months) "
            "VALUES (?, ?, ?, ?, ?)",
            ("WRX1", "X", "Odd", "continuous", "9,10,11"),
        )


def test_a_campaign_profile_with_months_lands(book: Database) -> None:
    book.execute(
        "INSERT INTO operating_profile (site_code, code, name, pattern, campaign_months) "
        "VALUES (?, ?, ?, ?, ?)",
        ("WRX1", "CAMP", "Beet campaign", "campaign", "9,10,11,12,1"),
    )
    assert book.scalar("SELECT COUNT(*) FROM operating_profile") == 2


def test_dropping_a_header_takes_its_stations(book: Database) -> None:
    station(book)
    book.execute("DELETE FROM header WHERE site_code = 'WRX1'")
    assert book.scalar("SELECT COUNT(*) FROM trap_station") == 0


def test_a_model_in_use_cannot_be_deleted(book: Database) -> None:
    station(book)
    with pytest.raises(sqlite3.IntegrityError):
        book.execute("DELETE FROM trap_model WHERE code = 'TD52'")


def test_the_indexes_are_there(book: Database) -> None:
    names = {
        str(row["name"])
        for row in book.query("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert {"station_by_header", "station_by_service", "station_by_model"} <= names
