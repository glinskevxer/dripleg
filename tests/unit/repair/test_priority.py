from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.errors import ValidationError
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import LossRegister, build_loss_register
from dripleg.model.attributes import Criticality
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.repair.priority import Priority, WorkList, rank_jobs, score_job
from dripleg.repair.recommend import RepairBasis, recommend
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from dripleg.units.money import Money
from tests.support.build import DAY, a_station, pipe, probe

BLOWING = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}
QUIET = {"ultrasonic": probe(4.0), "temperature": pipe(160.0, 130.0)}


def a_register(rows: list[tuple[str, dict[str, object], Criticality]]) -> LossRegister:
    register = TrapRegister(
        [a_station(tag=TrapTag.parse(tag), criticality=criticality) for tag, _, criticality in rows]
    )
    survey = Survey("WRX1", "S2025-1", "Spring", "Vane", DAY - dt.timedelta(days=1))
    for tag, readings, _ in rows:
        survey.record(
            Observation(
                tag=TrapTag.parse(tag),
                observed_on=DAY,
                technician="R Ellis",
                reported_condition=TrapCondition.OK,
                **readings,  # type: ignore[arg-type]
            )
        )
    return build_loss_register(
        register,
        diagnose_survey(register, survey),
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )


def a_work_list(rows: list[tuple[str, dict[str, object], Criticality]]) -> WorkList:
    register = a_register(rows)
    basis = RepairBasis.typical()
    return WorkList(rank_jobs([(row, recommend(row, basis)) for row in register.rows]))


def test_a_job_that_is_not_work_scores_nothing() -> None:
    register = a_register([("B12-MP-1", HEALTHY, Criticality.NUISANCE)])
    row = register.rows[0]
    assert score_job(row, recommend(row, RepairBasis.typical())) == 0.0


def test_a_real_job_scores_something() -> None:
    register = a_register([("B12-MP-1", BLOWING, Criticality.NUISANCE)])
    row = register.rows[0]
    assert score_job(row, recommend(row, RepairBasis.typical())) > 0.0


def test_criticality_lifts_the_score() -> None:
    quiet_line = a_register([("B12-MP-1", BLOWING, Criticality.NUISANCE)]).rows[0]
    busy_line = a_register([("B12-MP-1", BLOWING, Criticality.PRODUCTION)]).rows[0]
    basis = RepairBasis.typical()
    assert score_job(busy_line, recommend(busy_line, basis)) > score_job(
        quiet_line, recommend(quiet_line, basis)
    )


def test_a_safety_trap_holding_condensate_goes_straight_to_the_top() -> None:
    register = a_register([("B12-MP-1", QUIET, Criticality.SAFETY)])
    row = register.rows[0]
    ranked = rank_jobs([(row, recommend(row, RepairBasis.typical()))])
    assert ranked[0].priority is Priority.IMMEDIATE


def test_the_priority_bands_run_the_right_way() -> None:
    assert Priority.from_score(9.0) is Priority.IMMEDIATE
    assert Priority.from_score(2.5) is Priority.HIGH
    assert Priority.from_score(1.2) is Priority.MEDIUM
    assert Priority.from_score(0.4) is Priority.LOW
    assert Priority.from_score(0.0) is Priority.DEFERRED


def test_every_band_has_a_window() -> None:
    windows = [p.within_days for p in Priority]
    assert windows == sorted(windows)
    assert Priority.IMMEDIATE.within_days == 7


def test_jobs_rank_worst_first_and_then_by_tag() -> None:
    work = a_work_list(
        [
            ("B12-MP-2", BLOWING, Criticality.NUISANCE),
            ("B12-MP-1", BLOWING, Criticality.PRODUCTION),
            ("B12-MP-3", HEALTHY, Criticality.NUISANCE),
        ]
    )
    assert str(work.jobs[0].row.tag) == "B12-MP-0001"
    assert work.jobs[-1].score == 0.0


def test_only_real_jobs_count_towards_the_totals() -> None:
    work = a_work_list(
        [
            ("B12-MP-1", BLOWING, Criticality.NUISANCE),
            ("B12-MP-2", HEALTHY, Criticality.NUISANCE),
        ]
    )
    assert len(work) == 2
    assert len(work.actionable) == 1
    assert work.total_cost.cents > 0
    assert work.total_saving.cents > 0


def test_a_band_can_be_pulled_out() -> None:
    work = a_work_list([("B12-MP-1", HEALTHY, Criticality.NUISANCE)])
    assert len(work.in_band(Priority.DEFERRED)) == 1
    assert work.in_band(Priority.IMMEDIATE) == []


def test_a_budget_takes_the_top_of_the_list() -> None:
    work = a_work_list(
        [
            ("B12-MP-1", BLOWING, Criticality.PRODUCTION),
            ("B12-MP-2", BLOWING, Criticality.NUISANCE),
        ]
    )
    taken, left = work.within(work.jobs[0].cost)
    assert len(taken) == 1
    assert len(left) == 1
    assert taken[0].row.tag == work.jobs[0].row.tag


def test_a_budget_that_covers_everything_leaves_nothing() -> None:
    work = a_work_list([("B12-MP-1", BLOWING, Criticality.NUISANCE)])
    taken, left = work.within(Money.from_dollars("100000.00"))
    assert len(taken) == 1
    assert left == []


def test_a_budget_of_nothing_takes_nothing() -> None:
    work = a_work_list([("B12-MP-1", BLOWING, Criticality.NUISANCE)])
    taken, left = work.within(Money.zero())
    assert taken == []
    assert len(left) == 1


def test_a_negative_budget_is_refused() -> None:
    work = a_work_list([("B12-MP-1", BLOWING, Criticality.NUISANCE)])
    with pytest.raises(ValidationError, match="not negative"):
        work.within(Money.from_cents(-1))


def test_a_job_that_does_not_fit_is_skipped_rather_than_stopping_the_walk() -> None:
    work = a_work_list(
        [
            ("B12-MP-1", BLOWING, Criticality.SAFETY),
            ("B12-MP-2", BLOWING, Criticality.NUISANCE),
        ]
    )
    dearest = max(job.cost.cents for job in work.actionable)
    cheapest = min(job.cost.cents for job in work.actionable)
    if dearest != cheapest:
        taken, left = work.within(Money.from_cents(cheapest))
        assert len(taken) == 1
    else:
        taken, left = work.within(Money.from_cents(cheapest))
        assert len(taken) == 1
        assert len(left) == 1


def test_the_payback_on_a_chosen_set() -> None:
    work = a_work_list([("B12-MP-1", BLOWING, Criticality.NUISANCE)])
    taken, _ = work.within(Money.from_dollars("100000.00"))
    payback = work.payback_on(taken)
    assert payback is not None
    assert 0.0 < payback < 1.0
    assert work.payback_on([]) is None


def test_printing_a_ranked_job_and_a_work_list() -> None:
    work = a_work_list([("B12-MP-1", BLOWING, Criticality.NUISANCE)])
    assert str(work.jobs[0]).startswith("medium")
    printed = str(work)
    assert printed.startswith("1 jobs, $")
    assert "a year back" in printed
