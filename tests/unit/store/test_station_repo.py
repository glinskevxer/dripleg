from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import pytest

from dripleg.errors import NotFoundError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import ConnectionType, TrapModel
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area, Site
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.register import TrapRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.store.catalogue_repo import CatalogueRepository, ProfileRepository
from dripleg.store.db import Database
from dripleg.store.migrations import migrate
from dripleg.store.plant_repo import PlantRepository
from dripleg.store.station_repo import StationRepository
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

AREA = Area.of("WRX1", "B12", "Number 2 paper machine", "PM2")
MODEL = TrapModel(
    manufacturer="Halden",
    code="TD52",
    principle=OperatingPrinciple.THERMODYNAMIC_DISC,
    orifice_diameter_in=0.093,
    max_operating_pressure=Pressure.from_psig(600.0),
    max_back_pressure_percent=80.0,
    connection_size_in=0.5,
    connection_type=ConnectionType.SCREWED,
    list_price=Money.from_dollars("184.00"),
)
HEADER = SteamHeader.of(AREA, "MP", "Machine room main", 125.0, discharge_psig=15.0)
PROFILE = OperatingProfile.continuous()


@pytest.fixture
def repo() -> Iterator[StationRepository]:
    book = Database()
    migrate(book)
    plant = PlantRepository(book)
    plant.save_site(Site.of("WRX1", "Wrexham paper mill", "Bryn"))
    plant.save_area(AREA)
    plant.save_header(HEADER)
    CatalogueRepository(book).save(MODEL)
    ProfileRepository(book).save("WRX1", PROFILE)
    yield StationRepository(book)
    book.close()


def a_station(tag: str = "B12-MP-0043", **overrides: object) -> TrapInstallation:
    fields: dict[str, object] = {
        "site": SiteCode("WRX1"),
        "tag": TrapTag.parse(tag),
        "header": HEADER,
        "model": MODEL,
        "service": ServiceType.DRIP,
        "accessibility": Accessibility.GROUND_LEVEL,
        "criticality": Criticality.NUISANCE,
        "profile": PROFILE,
        "installed_on": dt.date(2021, 6, 14),
    }
    fields.update(overrides)
    return TrapInstallation(**fields)  # type: ignore[arg-type]


def test_a_station_round_trips(repo: StationRepository) -> None:
    repo.save(a_station())
    stored = repo.get("WRX1", "B12-MP-43")
    assert stored == a_station()


def test_every_field_survives_the_trip(repo: StationRepository) -> None:
    station = a_station(
        service=ServiceType.TRACER,
        accessibility=Accessibility.SCAFFOLD_REQUIRED,
        criticality=Criticality.SAFETY,
        destination=DischargeDestination.ATMOSPHERE,
        removed_on=dt.date(2024, 3, 1),
        strainer_fitted=False,
        isolation_valves=1,
        test_valve_fitted=True,
        insulated=False,
        interval_months_override=3,
        note="behind the second dryer, awkward",
    )
    repo.save(station)
    assert repo.get("WRX1", "B12-MP-43") == station


def test_saving_a_station_twice_updates_it(repo: StationRepository) -> None:
    repo.save(a_station())
    repo.save(a_station(service=ServiceType.UNIT_HEATER, note="changed"))
    stored = repo.get("WRX1", "B12-MP-43")
    assert stored.service is ServiceType.UNIT_HEATER
    assert stored.note == "changed"
    assert repo.count("WRX1") == 1


def test_a_missing_station(repo: StationRepository) -> None:
    with pytest.raises(NotFoundError, match="trap station"):
        repo.get("WRX1", "B12-MP-99")
    assert repo.find("WRX1", "B12-MP-99") is None


def test_deleting_a_station_says_whether_there_was_one(repo: StationRepository) -> None:
    repo.save(a_station())
    assert repo.delete("WRX1", "B12-MP-43")
    assert repo.count("WRX1") == 0
    assert not repo.delete("WRX1", "B12-MP-43")


def test_a_whole_register_goes_in_and_comes_back(repo: StationRepository) -> None:
    register = TrapRegister(
        [
            a_station("B12-MP-1"),
            a_station("B12-MP-2", service=ServiceType.TRACER),
            a_station("B12-MP-10", criticality=Criticality.PRODUCTION),
        ]
    )
    assert repo.save_register(register) == 3
    loaded = repo.load_register("WRX1")
    assert len(loaded) == 3
    assert [str(s.tag) for s in loaded] == ["B12-MP-0001", "B12-MP-0002", "B12-MP-0010"]
    assert loaded.get("B12-MP-2").service is ServiceType.TRACER


def test_a_loaded_register_carries_the_header_and_model(repo: StationRepository) -> None:
    repo.save(a_station())
    station = repo.load_register("WRX1").get("B12-MP-43")
    assert station.header.name == "Machine room main"
    assert station.model.code == "TD52"
    assert station.profile.code == "CONT"
    assert station.header.operating_pressure.psig == pytest.approx(125.0)


def test_an_empty_site_loads_an_empty_register(repo: StationRepository) -> None:
    assert len(repo.load_register("WRX1")) == 0
    assert repo.count("WRX1") == 0


def test_a_station_whose_header_went_missing_is_reported(repo: StationRepository) -> None:
    repo.save(a_station())
    repo.book.execute("PRAGMA foreign_keys = OFF")
    repo.book.execute("DELETE FROM header")
    with pytest.raises(NotFoundError, match="header"):
        repo.load_register("WRX1")


def test_a_station_whose_model_went_missing_is_reported(repo: StationRepository) -> None:
    repo.save(a_station())
    repo.book.execute("PRAGMA foreign_keys = OFF")
    repo.book.execute("DELETE FROM trap_model")
    with pytest.raises(NotFoundError, match="trap model"):
        repo.load_register("WRX1")


def test_a_station_whose_profile_went_missing_is_reported(repo: StationRepository) -> None:
    repo.save(a_station())
    repo.book.execute("PRAGMA foreign_keys = OFF")
    repo.book.execute("DELETE FROM operating_profile")
    with pytest.raises(NotFoundError, match="operating profile"):
        repo.load_register("WRX1")


def test_the_tag_columns_are_written_out_for_the_indexes(repo: StationRepository) -> None:
    repo.save(a_station("B12-MP-0043"))
    row = repo.book.one("SELECT area_code, system_code, sequence FROM trap_station")
    assert row is not None
    assert (row["area_code"], row["system_code"], row["sequence"]) == ("B12", "MP", 43)
