from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ConflictError, NotFoundError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import ConnectionType, TrapModel
from dripleg.model.header import SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.register import TrapRegister
from dripleg.model.tags import AreaCode, SiteCode, TrapTag
from dripleg.units.money import Money
from dripleg.units.pressure import Pressure

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


def header(area_code: str = "B12", system: str = "MP") -> SteamHeader:
    area = Area.of("WRX1", area_code, "Some area", "CC1")
    return SteamHeader.of(area, system, f"{system} main", 125.0, discharge_psig=15.0)


def station(
    tag: str,
    *,
    service: ServiceType = ServiceType.DRIP,
    criticality: Criticality = Criticality.NUISANCE,
    installed: dt.date = dt.date(2021, 6, 14),
    removed: dt.date | None = None,
) -> TrapInstallation:
    parsed = TrapTag.parse(tag)
    return TrapInstallation(
        site=SiteCode("WRX1"),
        tag=parsed,
        header=header(parsed.area.value, parsed.system.value),
        model=MODEL,
        service=service,
        accessibility=Accessibility.GROUND_LEVEL,
        criticality=criticality,
        profile=OperatingProfile.continuous(),
        installed_on=installed,
        removed_on=removed,
    )


def a_register() -> TrapRegister:
    return TrapRegister(
        [
            station("B12-MP-1"),
            station("B12-MP-2", service=ServiceType.TRACER),
            station("B12-LP-1", service=ServiceType.UNIT_HEATER),
            station("C3-MP-1", criticality=Criticality.PRODUCTION),
        ]
    )


def test_the_register_holds_and_returns_stations() -> None:
    register = a_register()
    assert len(register) == 4
    assert register.get("B12-MP-1").tag == TrapTag.parse("B12-MP-0001")
    assert register.get(TrapTag.parse("C3-MP-1")).criticality is Criticality.PRODUCTION


def test_a_duplicate_tag_is_refused() -> None:
    register = a_register()
    with pytest.raises(ConflictError, match="already on the register"):
        register.add(station("B12-MP-1"))


def test_a_missing_tag_raises_and_find_does_not() -> None:
    register = a_register()
    with pytest.raises(NotFoundError, match="trap station"):
        register.get("B12-MP-99")
    assert register.find("B12-MP-99") is None


def test_membership_takes_a_string_or_a_tag() -> None:
    register = a_register()
    assert "b12-mp-1" in register
    assert TrapTag.parse("B12-MP-0001") in register
    assert "B12-MP-77" not in register


def test_iterating_is_in_tag_order() -> None:
    assert [str(i.tag) for i in a_register()] == [
        "B12-LP-0001",
        "B12-MP-0001",
        "B12-MP-0002",
        "C3-MP-0001",
    ]
    assert a_register().tags[0] == TrapTag.parse("B12-LP-1")


def test_replacing_a_station_needs_it_to_be_there() -> None:
    register = a_register()
    retired = register.get("B12-MP-1").retired_on(dt.date(2025, 1, 1))
    register.replace(retired)
    assert register.get("B12-MP-1").is_removed
    with pytest.raises(NotFoundError, match="trap station"):
        TrapRegister().replace(retired)


def test_the_population_on_a_day_leaves_out_what_was_pulled() -> None:
    register = a_register()
    register.replace(register.get("B12-MP-2").retired_on(dt.date(2024, 5, 1)))
    live = register.in_service_on(dt.date(2025, 1, 1))
    assert [str(i.tag) for i in live] == ["B12-LP-0001", "B12-MP-0001", "C3-MP-0001"]
    assert len(register.in_service_on(dt.date(2024, 4, 30))) == 4
    assert len(register.in_service_on(dt.date(2020, 1, 1))) == 0


def test_slicing_by_area_and_system() -> None:
    register = a_register()
    assert len(register.in_area("B12")) == 3
    assert len(register.in_area(AreaCode("C3"))) == 1
    assert [str(i.tag) for i in register.on_system("B12", "MP")] == [
        "B12-MP-0001",
        "B12-MP-0002",
    ]


def test_slicing_by_header() -> None:
    register = a_register()
    on_lp = register.on_header(header("B12", "LP"))
    assert [str(i.tag) for i in on_lp] == ["B12-LP-0001"]


def test_slicing_by_service_and_criticality() -> None:
    register = a_register()
    assert len(register.with_service(ServiceType.DRIP)) == 2
    assert len(register.with_service(ServiceType.TRACER)) == 1
    assert len(register.with_criticality(Criticality.PRODUCTION)) == 1


def test_the_areas_and_headers_present() -> None:
    register = a_register()
    assert [str(a) for a in register.areas()] == ["B12", "C3"]
    assert [h.key for h in register.headers()] == [
        ("WRX1", "B12", "LP"),
        ("WRX1", "B12", "MP"),
        ("WRX1", "C3", "MP"),
    ]


def test_counting_by_area_and_by_service() -> None:
    register = a_register()
    assert {str(k): v for k, v in register.count_by_area().items()} == {"B12": 3, "C3": 1}
    counts = register.count_by_service()
    assert counts[ServiceType.DRIP] == 2
    assert counts[ServiceType.UNIT_HEATER] == 1


def test_counting_on_a_day_uses_the_live_population() -> None:
    register = a_register()
    register.replace(register.get("C3-MP-1").retired_on(dt.date(2024, 5, 1)))
    counts = register.count_by_area(on=dt.date(2025, 1, 1))
    assert {str(k): v for k, v in counts.items()} == {"B12": 3}
    assert register.count_by_service(on=dt.date(2025, 1, 1))[ServiceType.DRIP] == 1


def test_the_next_tag_carries_on_from_the_highest() -> None:
    register = a_register()
    assert str(register.next_tag_on("B12", "MP")) == "B12-MP-0003"
    assert str(register.next_tag_on("B12", "HP")) == "B12-HP-0001"


def test_an_empty_register_still_answers() -> None:
    empty = TrapRegister()
    assert len(empty) == 0
    assert empty.areas() == []
    assert empty.headers() == []
    assert empty.count_by_area() == {}
    assert str(empty.next_tag_on("B12", "MP")) == "B12-MP-0001"
