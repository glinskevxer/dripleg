from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area, Site
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.station_repo import StationRepository
from tests.support.build import a_model, a_station, header_for


@pytest.fixture
def repo() -> Iterator[StationRepository]:
    book = Database()
    migrate(book)
    plant = PlantRepository(book)
    plant.save_site(Site.of("WRX1", "Mill", "Bryn"))
    plant.save_area(Area.of("WRX1", "B12", "Machine", "PM2"))
    plant.save_header(header_for(TrapTag.parse("B12-MP-1")))
    CatalogueRepository(book).save(a_model())
    ProfileRepository(book).save("WRX1", OperatingProfile.continuous())
    yield StationRepository(book)
    book.close()


def a_batch(count: int) -> list:  # type: ignore[type-arg]
    return [a_station(tag=TrapTag.of("B12", "MP", n)) for n in range(1, count + 1)]


def test_a_batch_lands(repo: StationRepository) -> None:
    assert repo.save_many(a_batch(50)) == 50
    assert repo.count("WRX1") == 50


def test_a_batch_is_one_statement_however_many_rows(repo: StationRepository) -> None:
    repo.book.reset_statement_count()
    repo.save_many(a_batch(200))
    assert repo.book.statements == 1


def test_saving_one_at_a_time_is_one_statement_each(repo: StationRepository) -> None:
    repo.book.reset_statement_count()
    for station in a_batch(10):
        repo.save(station)
    assert repo.book.statements == 10


def test_an_empty_batch_writes_nothing(repo: StationRepository) -> None:
    repo.book.reset_statement_count()
    assert repo.save_many([]) == 0
    assert repo.book.statements == 0


def test_a_register_saves_through_the_batch(repo: StationRepository) -> None:
    register = TrapRegister(a_batch(30))
    repo.book.reset_statement_count()
    assert repo.save_register(register) == 30
    assert repo.book.statements == 1


def test_a_batch_upserts_the_same_as_one_at_a_time(repo: StationRepository) -> None:
    repo.save_many(a_batch(5))
    changed = [a_station(tag=TrapTag.of("B12", "MP", n), note="second pass") for n in range(1, 6)]
    repo.save_many(changed)
    assert repo.count("WRX1") == 5
    assert repo.get("WRX1", "B12-MP-1").note == "second pass"


def test_a_batch_round_trips_every_field(repo: StationRepository) -> None:
    station = a_station(
        tag=TrapTag.of("B12", "MP", 1),
        pipe_nominal="4",
        run_length_ft=180.0,
        removed_on=dt.date(2025, 1, 1),
        note="batched",
    )
    repo.save_many([station])
    assert repo.get("WRX1", "B12-MP-1") == station


def test_a_big_batch_loads_back_in_a_handful_of_queries(repo: StationRepository) -> None:
    repo.save_many(a_batch(400))
    repo.book.reset_statement_count()
    register = repo.load_register("WRX1")
    assert len(register) == 400
    assert repo.book.statements < 10


def test_the_statement_count_can_be_reset(repo: StationRepository) -> None:
    repo.save_many(a_batch(3))
    assert repo.book.statements > 0
    repo.book.reset_statement_count()
    assert repo.book.statements == 0
