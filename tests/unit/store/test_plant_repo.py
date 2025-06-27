from __future__ import annotations

from collections.abc import Iterator

import pytest

from dripleg.errors import NotFoundError, ValidationError
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.plant import Area, Site
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository


@pytest.fixture
def repo() -> Iterator[PlantRepository]:
    book = Database()
    migrate(book)
    yield PlantRepository(book)
    book.close()


def a_site() -> Site:
    return Site.of("WRX1", "Wrexham paper mill", "Bryn Paper Holdings")


def an_area(code: str = "B12", parent: str | None = None) -> Area:
    return Area.of("WRX1", code, f"Area {code}", "PM2", parent=parent)


def test_a_site_goes_in_and_comes_back(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    assert repo.get_site("WRX1") == a_site()


def test_saving_a_site_twice_updates_it(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_site(Site.of("WRX1", "Wrexham mill", "New Owner", programme_start_month=4))
    stored = repo.get_site("WRX1")
    assert stored.operator == "New Owner"
    assert stored.programme_start_month == 4
    assert len(repo.list_sites()) == 1


def test_a_missing_site(repo: PlantRepository) -> None:
    with pytest.raises(NotFoundError, match="site"):
        repo.get_site("NOPE")
    assert repo.find_site("NOPE") is None
    assert repo.find_site("WRX1") is None


def test_sites_list_in_code_order(repo: PlantRepository) -> None:
    repo.save_site(Site.of("WRX2", "Second", "Bryn"))
    repo.save_site(a_site())
    assert [str(s.code) for s in repo.list_sites()] == ["WRX1", "WRX2"]


def test_an_area_round_trips(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    assert repo.get_area("WRX1", "B12") == an_area()


def test_an_area_with_a_parent(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    repo.save_area(an_area("B12A", parent="B12"))
    children = repo.children_of("WRX1", "B12")
    assert [str(a.code) for a in children] == ["B12A"]
    assert repo.get_area("WRX1", "B12A").parent is not None


def test_saving_an_area_twice_updates_it(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    repo.save_area(Area.of("WRX1", "B12", "Renamed", "OTHER"))
    stored = repo.get_area("WRX1", "B12")
    assert stored.name == "Renamed"
    assert stored.cost_centre == "OTHER"
    assert len(repo.list_areas("WRX1")) == 1


def test_a_missing_area(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    with pytest.raises(NotFoundError, match="area"):
        repo.get_area("WRX1", "ZZ")


def test_a_header_round_trips_with_its_pressures(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    header = SteamHeader.of(an_area(), "MP", "Machine room main", 125.0, discharge_psig=15.0)
    repo.save_header(header)
    stored = repo.get_header("WRX1", "B12", "MP")
    assert stored.operating_pressure.psig == pytest.approx(125.0)
    assert stored.discharge_pressure.psig == pytest.approx(15.0)
    assert stored.destination is DischargeDestination.RETURN_LINE
    assert stored.name == "Machine room main"


def test_a_vented_header_keeps_its_destination(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    header = SteamHeader.of(
        an_area(), "LP", "Vent main", 15.0, destination=DischargeDestination.ATMOSPHERE
    )
    repo.save_header(header)
    assert repo.get_header("WRX1", "B12", "LP").destination is DischargeDestination.ATMOSPHERE


def test_saving_a_header_twice_updates_it(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    repo.save_header(SteamHeader.of(an_area(), "MP", "Main", 125.0))
    repo.save_header(SteamHeader.of(an_area(), "MP", "Main renamed", 100.0))
    stored = repo.get_header("WRX1", "B12", "MP")
    assert stored.name == "Main renamed"
    assert stored.operating_pressure.psig == pytest.approx(100.0)
    assert len(repo.list_headers("WRX1")) == 1


def test_headers_list_by_site_and_by_area(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    repo.save_area(an_area("C3"))
    repo.save_header(SteamHeader.of(an_area(), "MP", "Main", 125.0))
    repo.save_header(SteamHeader.of(an_area(), "LP", "Low", 15.0))
    repo.save_header(SteamHeader.of(an_area("C3"), "MP", "Other", 125.0))
    assert len(repo.list_headers("WRX1")) == 3
    assert [h.system.value for h in repo.list_headers("WRX1", "B12")] == ["LP", "MP"]


def test_a_missing_header(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    with pytest.raises(NotFoundError, match="header"):
        repo.get_header("WRX1", "B12", "MP")


def test_an_unknown_destination_in_the_book_is_caught(repo: PlantRepository) -> None:
    repo.save_site(a_site())
    repo.save_area(an_area())
    repo.save_header(SteamHeader.of(an_area(), "MP", "Main", 125.0))
    repo.book.execute("UPDATE header SET destination = 'somewhere'")
    with pytest.raises(ValidationError, match="not a discharge destination"):
        repo.get_header("WRX1", "B12", "MP")
