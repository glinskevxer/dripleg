from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import LossRegister, build_loss_register
from dripleg.model.attributes import ServiceType
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from dripleg.units.money import Money
from tests.support.build import DAY, a_station, pipe, probe

BLOWING = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}


def reading(tag: str, **fields: object) -> Observation:
    return Observation(
        tag=TrapTag.parse(tag),
        observed_on=DAY,
        technician="R Ellis",
        reported_condition=TrapCondition.OK,
        **fields,  # type: ignore[arg-type]
    )


def built(rows: list[tuple[str, dict[str, object], ServiceType]]) -> LossRegister:
    register = TrapRegister(
        [a_station(tag=TrapTag.parse(tag), service=service) for tag, _, service in rows]
    )
    survey = Survey("WRX1", "S2025-1", "Spring", "Vane", DAY - dt.timedelta(days=1))
    for tag, fields, _ in rows:
        survey.record(reading(tag, **fields))
    diagnosis = diagnose_survey(register, survey)
    return build_loss_register(
        register,
        diagnosis,
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )


def a_register() -> LossRegister:
    return built(
        [
            ("B12-MP-1", BLOWING, ServiceType.DRIP),
            ("B12-MP-2", HEALTHY, ServiceType.DRIP),
            ("C3-MP-1", BLOWING, ServiceType.TRACER),
        ]
    )


def test_every_trap_gets_a_row_including_the_healthy_ones() -> None:
    register = a_register()
    assert len(register) == 3
    assert len(register.losing) == 2
    assert register.loss_rate == pytest.approx(2 / 3)


def test_rows_come_back_in_tag_order() -> None:
    assert [str(row.tag) for row in a_register().rows] == [
        "B12-MP-0001",
        "B12-MP-0002",
        "C3-MP-0001",
    ]


def test_the_totals_add_the_rows_up() -> None:
    register = a_register()
    assert register.total_cost.cents == sum(row.annual_cost.cents for row in register.rows)
    assert register.total_mass.pounds == pytest.approx(
        sum(row.steam.pounds_per_year for row in register.rows)
    )
    assert register.total_flow.pounds_per_hour > 0
    assert register.total_fuel.mmbtu > 0
    assert register.total_tonnes_co2e > 0


def test_an_empty_register_totals_to_nothing() -> None:
    empty = LossRegister("S2025-1", [])
    assert len(empty) == 0
    assert empty.total_cost == Money.zero()
    assert empty.total_mass.pounds == 0.0
    assert empty.total_flow.is_zero
    assert empty.loss_rate == 0.0
    assert empty.top_losers() == []
    assert empty.cost_by_area() == {}


def test_the_top_losers_are_the_dearest_first() -> None:
    register = a_register()
    top = register.top_losers(1)
    assert len(top) == 1
    assert top[0].annual_cost.cents == max(row.annual_cost.cents for row in register.rows)


def test_a_healthy_trap_is_never_a_top_loser() -> None:
    top = a_register().top_losers(10)
    assert all(row.is_losing for row in top)
    assert len(top) == 2


def test_the_cost_splits_by_area() -> None:
    by_area = a_register().cost_by_area()
    assert [str(a) for a in by_area] == ["B12", "C3"]
    assert sum(m.cents for m in by_area.values()) == a_register().total_cost.cents


def test_the_cost_splits_by_service_dearest_first() -> None:
    by_service = a_register().cost_by_service()
    values = list(by_service.values())
    assert values == sorted(values, key=lambda m: -m.cents)


def test_the_cost_splits_by_condition_worst_first() -> None:
    by_condition = a_register().cost_by_condition()
    assert list(by_condition)[0] is TrapCondition.BLOWING_THROUGH
    assert by_condition[TrapCondition.OK] == Money.zero()


def test_a_row_can_be_found_and_its_share_taken() -> None:
    register = a_register()
    row = register.find("B12-MP-1")
    assert row is not None
    assert register.find("B12-MP-99") is None
    assert 0.0 < register.share_of_total(row) < 1.0
    shares = [register.share_of_total(r) for r in register.rows]
    assert sum(shares) == pytest.approx(1.0)


def test_the_share_of_a_register_that_lost_nothing() -> None:
    register = built([("B12-MP-1", HEALTHY, ServiceType.DRIP)])
    row = register.rows[0]
    assert register.share_of_total(row) == 0.0


def test_a_row_carries_the_whole_chain() -> None:
    row = a_register().find("B12-MP-1")
    assert row is not None
    assert row.condition is TrapCondition.BLOWING_THROUGH
    assert row.diagnosis.confidence > 0.5
    assert row.steam.flow.pounds_per_hour > 0
    assert row.heat.mmbtu_per_year > 0
    assert row.cost.fuel.cents > 0
    assert row.stack.tonnes_co2e > 0
    assert row.area.value == "B12"
    assert row.service is ServiceType.DRIP


def test_printing_a_row_and_a_register() -> None:
    register = a_register()
    losing = register.find("B12-MP-1")
    healthy = register.find("B12-MP-2")
    assert losing is not None
    assert healthy is not None
    assert str(losing).startswith("B12-MP-0001 blowing through, $")
    assert str(healthy) == "B12-MP-0002 ok, nothing lost"
    assert str(register).startswith("S2025-1: 2 of 3 losing, $")
