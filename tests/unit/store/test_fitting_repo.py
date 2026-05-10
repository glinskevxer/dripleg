from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import replace

import pytest

from dripleg.errors import ConflictError, ValidationError
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area, Site
from dripleg.model.tags import TrapTag
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.db import Database
from dripleg.store.fitting_repo import Fitting, FittingRepository
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.station_repo import StationRepository
from tests.support.build import a_model, a_station, header_for

FITTED = dt.date(2021, 6, 14)


@pytest.fixture
def book() -> Iterator[Database]:
    db = Database()
    migrate(db)
    plant = PlantRepository(db)
    plant.save_site(Site.of("WRX1", "Mill", "Bryn"))
    plant.save_area(Area.of("WRX1", "B12", "Machine", "PM2"))
    plant.save_header(header_for(TrapTag.parse("B12-MP-1")))
    catalogue = CatalogueRepository(db)
    catalogue.save(a_model())
    catalogue.save(replace(a_model(), code="TD75", warranty_months=36))
    ProfileRepository(db).save("WRX1", OperatingProfile.continuous())
    StationRepository(db).save(a_station(tag=TrapTag.parse("B12-MP-1")))
    yield db
    db.close()


def test_a_fitting_carries_its_warranty_window() -> None:
    fitting = Fitting(TrapTag.parse("B12-MP-1"), FITTED, "HALDEN", "TD52", 12)
    assert fitting.warranty_ends == dt.date(2022, 6, 14)
    assert fitting.is_in_warranty_on(dt.date(2022, 6, 13))
    assert not fitting.is_in_warranty_on(dt.date(2022, 6, 14))


def test_a_fitting_with_no_warranty_is_never_in_one() -> None:
    fitting = Fitting(TrapTag.parse("B12-MP-1"), FITTED, "HALDEN", "TD52", 0)
    assert not fitting.is_in_warranty_on(FITTED)


def test_a_fitting_checks_itself() -> None:
    with pytest.raises(ValidationError, match="names a model"):
        Fitting(TrapTag.parse("B12-MP-1"), FITTED, "  ", "TD52")
    with pytest.raises(ValidationError, match="not negative"):
        Fitting(TrapTag.parse("B12-MP-1"), FITTED, "HALDEN", "TD52", -1)


def test_the_age_never_goes_backwards() -> None:
    fitting = Fitting(TrapTag.parse("B12-MP-1"), FITTED, "HALDEN", "TD52")
    assert fitting.age_days_on(FITTED + dt.timedelta(days=100)) == 100
    assert fitting.age_days_on(FITTED - dt.timedelta(days=100)) == 0


def test_a_fitting_round_trips(book: Database) -> None:
    repo = FittingRepository(book)
    repo.record("WRX1", "B12-MP-1", a_model(), FITTED, "WO-00001")
    history = repo.history_for("WRX1", "B12-MP-1")
    assert len(history) == 1
    assert history[0].model_code == "TD52"
    assert history[0].work_order == "WO-00001"
    assert history[0].warranty_months == 12


def test_a_fitting_on_a_station_that_is_not_there(book: Database) -> None:
    with pytest.raises(ConflictError, match="not a station"):
        FittingRepository(book).record("WRX1", "B12-MP-9", a_model(), FITTED)


def test_the_history_comes_back_oldest_first(book: Database) -> None:
    repo = FittingRepository(book)
    repo.record("WRX1", "B12-MP-1", replace(a_model(), code="TD75"), dt.date(2024, 3, 1))
    repo.record("WRX1", "B12-MP-1", a_model(), FITTED)
    history = repo.history_for("WRX1", "B12-MP-1")
    assert [f.fitted_on for f in history] == [FITTED, dt.date(2024, 3, 1)]


def test_recording_the_same_day_twice_updates_it(book: Database) -> None:
    repo = FittingRepository(book)
    repo.record("WRX1", "B12-MP-1", a_model(), FITTED)
    repo.record("WRX1", "B12-MP-1", replace(a_model(), code="TD75"), FITTED)
    history = repo.history_for("WRX1", "B12-MP-1")
    assert len(history) == 1
    assert history[0].model_code == "TD75"


def test_the_newest_fitting_decides_the_warranty(book: Database) -> None:
    repo = FittingRepository(book)
    repo.record("WRX1", "B12-MP-1", a_model(), FITTED)
    repo.record("WRX1", "B12-MP-1", replace(a_model(), code="TD75"), dt.date(2025, 4, 2))
    live = repo.in_warranty_on("WRX1", dt.date(2026, 1, 1))
    assert len(live) == 1
    assert live[0].model_code == "TD75"
    assert live[0].warranty_months == 36


def test_a_trap_out_of_warranty_is_left_out(book: Database) -> None:
    repo = FittingRepository(book)
    repo.record("WRX1", "B12-MP-1", a_model(), FITTED)
    assert repo.in_warranty_on("WRX1", dt.date(2026, 1, 1)) == []


def test_the_service_lives_are_the_gaps_between_fittings(book: Database) -> None:
    repo = FittingRepository(book)
    repo.record("WRX1", "B12-MP-1", a_model(), dt.date(2021, 1, 1))
    repo.record("WRX1", "B12-MP-1", a_model(), dt.date(2023, 1, 1))
    repo.record("WRX1", "B12-MP-1", a_model(), dt.date(2024, 1, 1))
    lives = repo.service_lives("WRX1")
    assert lives[TrapTag.parse("B12-MP-1")] == [730, 365]


def test_a_station_fitted_once_has_no_service_life_yet(book: Database) -> None:
    repo = FittingRepository(book)
    repo.record("WRX1", "B12-MP-1", a_model(), FITTED)
    assert repo.service_lives("WRX1") == {}


def test_the_history_goes_when_the_station_goes(book: Database) -> None:
    FittingRepository(book).record("WRX1", "B12-MP-1", a_model(), FITTED)
    book.execute("DELETE FROM trap_station")
    assert book.scalar("SELECT COUNT(*) FROM trap_fitting") == 0


def test_printing_a_fitting() -> None:
    fitting = Fitting(TrapTag.parse("B12-MP-1"), FITTED, "HALDEN", "TD52")
    assert str(fitting) == "HALDEN TD52 fitted to B12-MP-0001 on 2021-06-14"
