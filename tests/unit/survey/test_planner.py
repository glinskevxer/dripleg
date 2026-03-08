from __future__ import annotations

import pytest

from dripleg.errors import ValidationError
from dripleg.model.attributes import Accessibility
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.survey.planner import (
    needs_arranging,
    permit_stations,
    plan_routes,
)
from tests.support.build import a_station


def a_register(rows: list[tuple[str, Accessibility]]) -> TrapRegister:
    return TrapRegister(
        [a_station(tag=TrapTag.parse(tag), accessibility=access) for tag, access in rows]
    )


def ground(tags: list[str]) -> TrapRegister:
    return a_register([(tag, Accessibility.GROUND_LEVEL) for tag in tags])


def test_a_register_is_cut_by_area_and_system() -> None:
    plan = plan_routes(ground(["B12-MP-1", "B12-MP-2", "B12-LP-1", "C3-MP-1"]), "WRX1")
    assert [route.name for route in plan.routes] == ["B12 LP", "B12 MP", "C3 MP"]
    assert plan.covered == 4


def test_stops_come_out_in_tag_order() -> None:
    plan = plan_routes(ground(["B12-MP-10", "B12-MP-2", "B12-MP-1"]), "WRX1")
    assert [str(tag) for tag in plan.routes[0].stops] == [
        "B12-MP-0001",
        "B12-MP-0002",
        "B12-MP-0010",
    ]


def test_routes_are_numbered_in_order() -> None:
    plan = plan_routes(ground(["B12-MP-1", "C3-MP-1"]), "WRX1")
    assert [route.code for route in plan.routes] == ["R01", "R02"]


def test_the_prefix_can_be_changed() -> None:
    plan = plan_routes(ground(["B12-MP-1"]), "WRX1", prefix="WALK")
    assert plan.routes[0].code == "WALK01"


def test_a_long_system_is_cut_into_parts() -> None:
    tags = [f"B12-MP-{n}" for n in range(1, 15)]
    plan = plan_routes(ground(tags), "WRX1", shift_hours=1.5, minutes_per_stop=6.0)
    assert len(plan) == 2
    assert [route.name for route in plan.routes] == ["B12 MP part 1", "B12 MP part 2"]
    assert [len(route) for route in plan.routes] == [10, 4]
    assert plan.covered == 14


def test_a_short_system_is_not_labelled_as_a_part() -> None:
    plan = plan_routes(ground(["B12-MP-1"]), "WRX1")
    assert plan.routes[0].name == "B12 MP"


def test_every_route_fits_inside_the_shift() -> None:
    tags = [f"B12-MP-{n}" for n in range(1, 40)]
    plan = plan_routes(ground(tags), "WRX1", shift_hours=2.0)
    assert all(route.estimated_hours <= 2.0 for route in plan.routes)


def test_the_hard_to_reach_stations_are_set_aside() -> None:
    register = a_register(
        [
            ("B12-MP-1", Accessibility.GROUND_LEVEL),
            ("B12-MP-2", Accessibility.SCAFFOLD_REQUIRED),
            ("B12-MP-3", Accessibility.SHUTDOWN_ONLY),
        ]
    )
    plan = plan_routes(register, "WRX1")
    assert plan.covered == 1
    assert [str(tag) for tag in plan.set_aside] == ["B12-MP-0002", "B12-MP-0003"]


def test_a_ladder_is_still_an_ordinary_stop() -> None:
    plan = plan_routes(a_register([("B12-MP-1", Accessibility.LADDER)]), "WRX1")
    assert plan.covered == 1
    assert plan.set_aside == []


def test_the_hours_add_the_routes_up() -> None:
    plan = plan_routes(ground(["B12-MP-1", "C3-MP-1"]), "WRX1")
    assert plan.hours == pytest.approx(sum(r.estimated_hours for r in plan.routes))


def test_a_shift_that_fits_nothing_is_refused() -> None:
    with pytest.raises(ValidationError, match="no stops fit"):
        plan_routes(ground(["B12-MP-1"]), "WRX1", shift_hours=0.4, walk_minutes=30.0)


def test_a_daft_shift_or_stop_time_is_refused() -> None:
    with pytest.raises(ValidationError, match="longer than nothing"):
        plan_routes(ground(["B12-MP-1"]), "WRX1", shift_hours=0.0)
    with pytest.raises(ValidationError, match="takes some time"):
        plan_routes(ground(["B12-MP-1"]), "WRX1", minutes_per_stop=0.0)


def test_an_empty_register_plans_nothing() -> None:
    plan = plan_routes(TrapRegister(), "WRX1")
    assert len(plan) == 0
    assert plan.covered == 0
    assert plan.hours == 0.0


def test_what_needs_arranging_is_listed_separately() -> None:
    register = a_register(
        [
            ("B12-MP-1", Accessibility.GROUND_LEVEL),
            ("B12-MP-2", Accessibility.CONFINED_SPACE),
            ("B12-MP-3", Accessibility.CONFINED_SPACE),
            ("B12-MP-4", Accessibility.SHUTDOWN_ONLY),
        ]
    )
    assert [str(t) for t in needs_arranging(register)] == [
        "B12-MP-0002",
        "B12-MP-0003",
        "B12-MP-0004",
    ]
    grouped = permit_stations(register)
    assert set(grouped) == {Accessibility.CONFINED_SPACE, Accessibility.SHUTDOWN_ONLY}
    assert len(grouped[Accessibility.CONFINED_SPACE]) == 2


def test_a_register_everybody_can_reach_needs_nothing_arranged() -> None:
    assert needs_arranging(ground(["B12-MP-1"])) == []
    assert permit_stations(ground(["B12-MP-1"])) == {}


def test_printing_a_plan() -> None:
    plan = plan_routes(ground(["B12-MP-1", "C3-MP-1"]), "WRX1")
    printed = str(plan)
    assert printed.startswith("2 routes covering 2 traps in ")
    assert printed.endswith("0 set aside")
