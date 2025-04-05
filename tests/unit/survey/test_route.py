from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ConflictError, NotFoundError, ValidationError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.catalogue import ConnectionType, TrapModel
from dripleg.model.header import SteamHeader
from dripleg.model.installation import TrapInstallation
from dripleg.model.operating import OperatingProfile
from dripleg.model.plant import Area
from dripleg.model.principles import OperatingPrinciple
from dripleg.model.register import TrapRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.survey.route import Route, unrouted_tags
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


def a_register(tags: list[str]) -> TrapRegister:
    stations = []
    for text in tags:
        tag = TrapTag.parse(text)
        area = Area.of("WRX1", tag.area.value, "Area", "CC1")
        stations.append(
            TrapInstallation(
                site=SiteCode("WRX1"),
                tag=tag,
                header=SteamHeader.of(area, tag.system.value, "Main", 125.0),
                model=MODEL,
                service=ServiceType.DRIP,
                accessibility=Accessibility.GROUND_LEVEL,
                criticality=Criticality.NUISANCE,
                profile=OperatingProfile.continuous(),
                installed_on=dt.date(2021, 6, 14),
            )
        )
    return TrapRegister(stations)


def a_route(stops: list[str] | None = None) -> Route:
    return Route.of("WRX1", "r1", "Machine room ground floor", stops)


def test_a_route_normalises_its_code_and_name() -> None:
    route = Route.of("WRX1", " r1 ", "  Machine   room ")
    assert route.code == "R1"
    assert route.name == "Machine room"


def test_a_route_needs_a_code_and_a_name() -> None:
    with pytest.raises(ValidationError, match="needs a code"):
        Route.of("WRX1", "  ", "Machine room")
    with pytest.raises(ValidationError, match="needs a name"):
        Route.of("WRX1", "R1", " ")


def test_a_route_keeps_the_order_it_was_given() -> None:
    route = a_route(["B12-MP-10", "B12-MP-2", "B12-LP-1"])
    assert [str(t) for t in route.stops] == ["B12-MP-0010", "B12-MP-0002", "B12-LP-0001"]
    assert len(route) == 3


def test_a_tag_cannot_be_on_a_route_twice() -> None:
    with pytest.raises(ValidationError, match="on this route twice"):
        a_route(["B12-MP-1", "B12-MP-0001"])


def test_membership_takes_a_string_or_a_tag() -> None:
    route = a_route(["B12-MP-1"])
    assert "b12-mp-0001" in route
    assert TrapTag.parse("B12-MP-1") in route
    assert "B12-MP-9" not in route


def test_the_areas_a_route_touches() -> None:
    route = a_route(["C3-MP-1", "B12-MP-1"])
    assert [str(a) for a in route.areas] == ["B12", "C3"]


def test_the_time_estimate_is_the_walk_plus_the_stops() -> None:
    route = a_route(["B12-MP-1", "B12-MP-2"])
    assert route.estimated_minutes == pytest.approx(30.0 + 12.0)
    assert route.estimated_hours == pytest.approx(0.7)


def test_the_time_estimate_can_be_tuned() -> None:
    route = a_route(["B12-MP-1"])
    route.minutes_per_stop = 12.0
    route.walk_minutes = 0.0
    assert route.estimated_minutes == pytest.approx(12.0)


def test_bad_timings_are_refused() -> None:
    with pytest.raises(ValidationError, match="takes some time"):
        Route(site=SiteCode("WRX1"), code="R1", name="A", minutes_per_stop=0.0)
    with pytest.raises(ValidationError, match="not negative"):
        Route(site=SiteCode("WRX1"), code="R1", name="A", walk_minutes=-1.0)


def test_finding_a_stop_and_missing_one() -> None:
    route = a_route(["B12-MP-1", "B12-MP-2"])
    assert route.position_of("B12-MP-2") == 1
    with pytest.raises(NotFoundError, match="stop"):
        route.position_of("B12-MP-9")


def test_adding_a_stop_at_the_end_and_in_the_middle() -> None:
    route = a_route(["B12-MP-1", "B12-MP-3"])
    route.add_stop("B12-MP-4")
    route.add_stop("B12-MP-2", after="B12-MP-1")
    assert [t.sequence for t in route.stops] == [1, 2, 3, 4]


def test_adding_a_stop_that_is_already_there() -> None:
    route = a_route(["B12-MP-1"])
    with pytest.raises(ConflictError, match="already on route"):
        route.add_stop("B12-MP-0001")


def test_dropping_a_stop_leaves_the_rest_in_order() -> None:
    route = a_route(["B12-MP-1", "B12-MP-2", "B12-MP-3"])
    route.drop_stop("B12-MP-2")
    assert [t.sequence for t in route.stops] == [1, 3]
    with pytest.raises(NotFoundError, match="stop"):
        route.drop_stop("B12-MP-2")


def test_splitting_a_route_across_days_keeps_the_order() -> None:
    route = a_route([f"B12-MP-{n}" for n in range(1, 8)])
    pieces = route.split(3)
    assert [len(p) for p in pieces] == [3, 3, 1]
    assert [t.sequence for t in pieces[0]] == [1, 2, 3]


def test_splitting_into_one_day_is_the_whole_route() -> None:
    route = a_route(["B12-MP-1", "B12-MP-2"])
    assert route.split(1) == [route.stops]


def test_splitting_an_empty_route_gives_empty_days() -> None:
    assert a_route().split(2) == [[], []]


def test_splitting_into_no_days_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least one day"):
        a_route(["B12-MP-1"]).split(0)


def test_stops_that_are_no_longer_stations() -> None:
    register = a_register(["B12-MP-1", "B12-MP-2"])
    route = a_route(["B12-MP-1", "B12-MP-9"])
    assert [str(t) for t in route.missing_from(register)] == ["B12-MP-0009"]


def test_stations_that_no_route_visits() -> None:
    register = a_register(["B12-MP-1", "B12-MP-2", "C3-MP-1"])
    routes = [a_route(["B12-MP-1"]), Route.of("WRX1", "R2", "Second", ["C3-MP-1"])]
    assert [str(t) for t in unrouted_tags(register, routes)] == ["B12-MP-0002"]


def test_everything_routed_leaves_no_hole() -> None:
    register = a_register(["B12-MP-1"])
    assert unrouted_tags(register, [a_route(["B12-MP-1"])]) == []


def test_a_route_that_is_too_long() -> None:
    tags = [f"B12-MP-{n}" for n in range(1, 402)]
    with pytest.raises(ValidationError, match="stops at 400"):
        a_route(tags)
    route = a_route(tags[:400])
    with pytest.raises(ValidationError, match="stops at 400"):
        route.add_stop("B12-LP-1")


def test_printing_a_route() -> None:
    assert str(a_route(["B12-MP-1"])) == "R1 Machine room ground floor (1 stops)"
