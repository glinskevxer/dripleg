from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.errors import ValidationError
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import build_loss_register
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.repair.priority import WorkList, rank_jobs
from dripleg.repair.recommend import RepairBasis, recommend
from dripleg.repair.spares import SparesLine, build_spares_list
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from dripleg.units.money import Money
from tests.support.build import DAY, a_station, pipe, probe

BLOWING: dict[str, object] = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY: dict[str, object] = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}
RESTRICTED: dict[str, object] = {"ultrasonic": probe(20.0), "temperature": pipe(300.0, 200.0)}


def a_work_list(rows: list[tuple[str, dict[str, object]]]) -> WorkList:
    register = TrapRegister([a_station(tag=TrapTag.parse(tag)) for tag, _ in rows])
    survey = Survey("WRX1", "S2025-1", "Spring", "Vane", DAY - dt.timedelta(days=1))
    for tag, readings in rows:
        survey.record(
            Observation(
                tag=TrapTag.parse(tag),
                observed_on=DAY,
                technician="R Ellis",
                reported_condition=TrapCondition.OK,
                **readings,  # type: ignore[arg-type]
            )
        )
    losses = build_loss_register(
        register,
        diagnose_survey(register, survey),
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )
    basis = RepairBasis.typical()
    return WorkList(rank_jobs([(row, recommend(row, basis)) for row in losses.rows]))


def test_a_repair_needs_a_kit() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", BLOWING)]))
    assert len(spares.lines) == 1
    line = spares.lines[0]
    assert line.part == "repair kit"
    assert line.code == "TD52"
    assert line.jobs == 1


def test_several_repairs_on_one_model_make_one_line() -> None:
    spares = build_spares_list(
        a_work_list([("B12-MP-1", BLOWING), ("B12-MP-2", BLOWING), ("B12-MP-3", BLOWING)])
    )
    assert len(spares.lines) == 1
    assert spares.lines[0].jobs == 3


def test_a_single_job_orders_a_single_part() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", BLOWING)]), allowance=0.10)
    assert spares.lines[0].quantity == 1
    assert spares.lines[0].spare == 0


def test_the_allowance_rounds_down_across_a_batch() -> None:
    spares = build_spares_list(
        a_work_list([(f"B12-MP-{n}", BLOWING) for n in range(1, 11)]), allowance=0.10
    )
    line = spares.lines[0]
    assert line.jobs == 10
    assert line.quantity == 11
    assert line.spare == 1


def test_no_allowance_orders_exactly_what_is_needed() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", BLOWING)]), allowance=0.0)
    assert spares.lines[0].quantity == 1
    assert spares.lines[0].spare == 0


def test_an_allowance_outside_the_range_is_refused() -> None:
    with pytest.raises(ValidationError, match="allowance sits in"):
        build_spares_list(a_work_list([("B12-MP-1", BLOWING)]), allowance=1.5)


def test_a_cleaning_job_needs_nothing() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", RESTRICTED)]))
    assert spares.lines == []
    assert spares.jobs_needing_nothing == 1
    assert spares.total.is_zero


def test_a_healthy_trap_is_not_on_the_list_at_all() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", HEALTHY)]))
    assert spares.lines == []
    assert spares.jobs_needing_nothing == 0


def test_the_total_is_the_lines_added_up() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", BLOWING), ("B12-MP-2", BLOWING)]))
    assert spares.total.cents == sum(line.total.cents for line in spares.lines)
    assert spares.parts == sum(line.quantity for line in spares.lines)


def test_lines_come_back_dearest_first() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", BLOWING), ("B12-MP-2", BLOWING)]))
    totals = [line.total.cents for line in spares.lines]
    assert totals == sorted(totals, reverse=True)


def test_a_part_can_be_pulled_out_by_name() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", BLOWING)]))
    assert len(spares.of_part("repair kit")) == 1
    assert spares.of_part("trap") == []


def test_a_line_checks_its_own_arithmetic() -> None:
    with pytest.raises(ValidationError, match="at least one job"):
        SparesLine(
            "HALDEN", "TD52", "trap", jobs=0, quantity=1, unit_price=Money.from_dollars("1.00")
        )
    with pytest.raises(ValidationError, match="fewer parts than jobs"):
        SparesLine(
            "HALDEN", "TD52", "trap", jobs=3, quantity=2, unit_price=Money.from_dollars("1.00")
        )


def test_printing_a_line_and_a_list() -> None:
    spares = build_spares_list(a_work_list([("B12-MP-1", BLOWING)]))
    assert str(spares.lines[0]).startswith("1 x HALDEN TD52 repair kit for 1 jobs, $")
    assert str(spares).startswith("1 lines, 1 parts, $")
    assert str(spares).endswith("0 jobs needing nothing")
