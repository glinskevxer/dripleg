from __future__ import annotations

from collections.abc import Iterator

import pytest

from dripleg.store.db import Database
from dripleg.store.migrations import migrate


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    yield db
    db.close()


def test_the_new_columns_land(book: Database) -> None:
    columns = book.column_names("trap_station")
    for name in ("pipe_nominal", "run_length_ft", "warmup_minutes"):
        assert name in columns


def test_the_new_columns_come_last(book: Database) -> None:
    columns = book.column_names("trap_station")
    assert columns[-4:] == ["pipe_nominal", "run_length_ft", "warmup_minutes", "note"] or (
        columns[-3:] == ["pipe_nominal", "run_length_ft", "warmup_minutes"]
    )


def test_the_new_columns_are_optional(book: Database) -> None:
    book.execute(
        "INSERT INTO site (code, name, operator, fuel_price_basis) VALUES (?, ?, ?, ?)",
        ("WRX1", "Mill", "Bryn", "gas"),
    )
    book.execute(
        "INSERT INTO area (site_code, code, name, cost_centre) VALUES (?, ?, ?, ?)",
        ("WRX1", "B12", "Machine", "CC1"),
    )
    book.execute(
        "INSERT INTO header (site_code, area_code, system_code, name, operating_psia, "
        "design_psia, discharge_psia, destination) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("WRX1", "B12", "MP", "Main", 139.7, 170.0, 29.7, "return"),
    )
    book.execute(
        "INSERT INTO operating_profile (site_code, code, name, pattern) VALUES (?, ?, ?, ?)",
        ("WRX1", "CONT", "Continuous", "continuous"),
    )
    book.execute(
        "INSERT INTO trap_model (manufacturer, code, principle, orifice_diameter_in, "
        "max_operating_psia, max_back_pressure_pct, connection_size_in, connection_type, "
        "list_price_cents) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("HALDEN", "TD52", "thermodynamic_disc", 0.093, 614.7, 80.0, 0.5, "screwed", 18400),
    )
    book.execute(
        "INSERT INTO trap_station (site_code, tag, area_code, system_code, sequence, "
        "model_manufacturer, model_code, service, accessibility, criticality, "
        "profile_code, installed_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "WRX1",
            "B12-MP-0043",
            "B12",
            "MP",
            43,
            "HALDEN",
            "TD52",
            "drip",
            "ground_level",
            "nuisance",
            "CONT",
            "2021-06-14",
        ),
    )
    assert book.scalar("SELECT pipe_nominal FROM trap_station") is None
    assert book.scalar("SELECT warmup_minutes FROM trap_station") is None


def test_the_migration_is_the_sixth(book: Database) -> None:
    numbers = [int(row["number"]) for row in book.query("SELECT number FROM schema_migration")]
    assert 6 in numbers
    assert max(numbers) >= 6
