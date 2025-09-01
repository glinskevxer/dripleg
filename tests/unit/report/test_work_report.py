from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import build_loss_register
from dripleg.model.attributes import Criticality
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.repair.priority import Priority, WorkList, rank_jobs
from dripleg.repair.recommend import RepairBasis, recommend
from dripleg.report.work_report import build_work_report
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from dripleg.units.money import Money
from tests.support.build import DAY, a_station, pipe, probe

BLOWING = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}


def a_work_list(rows: list[tuple[str, dict[str, object], Criticality]]) -> WorkList:
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
    loss = build_loss_register(
        register,
        diagnose_survey(register, survey),
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )
    basis = RepairBasis.typical()
    return WorkList(rank_jobs([(row, recommend(row, basis)) for row in loss.rows]))


def a_list() -> WorkList:
    return a_work_list(
        [
            ("B12-MP-1", BLOWING, Criticality.PRODUCTION),
            ("B12-MP-2", BLOWING, Criticality.NUISANCE),
            ("B12-MP-3", HEALTHY, Criticality.NUISANCE),
        ]
    )


def test_only_real_jobs_reach_the_report() -> None:
    report = build_work_report("WRX1", a_list())
    assert report.jobs == 2
    assert all(line.action == "repair" for line in report.lines_in)


def test_the_running_totals_climb_down_the_list() -> None:
    report = build_work_report("WRX1", a_list())
    first, second = report.lines_in
    assert second.cumulative_cost.cents == first.cost.cents + second.cost.cents
    assert second.cumulative_saving.cents == first.saving.cents + second.saving.cents
    assert report.total_cost == second.cumulative_cost
    assert report.total_saving == second.cumulative_saving


def test_without_a_budget_every_job_is_inside_it() -> None:
    report = build_work_report("WRX1", a_list())
    assert report.budget is None
    assert len(report.inside) == 2
    assert report.outside == []
    assert "jobs, $" in report.headline


def test_a_budget_draws_a_line_across_the_list() -> None:
    work = a_list()
    cheapest = min(job.cost.cents for job in work.actionable)
    report = build_work_report("WRX1", work, Money.from_cents(cheapest))
    assert len(report.inside) == 1
    assert len(report.outside) == 1
    assert "inside $" in report.headline
    assert "fall outside the budget" in report.render()


def test_a_budget_that_covers_everything_leaves_no_remainder() -> None:
    report = build_work_report("WRX1", a_list(), Money.from_dollars("100000.00"))
    assert report.outside == []
    assert "fall outside" not in report.render()


def test_the_report_can_be_cut_to_one_band() -> None:
    work = a_list()
    bands = {job.priority for job in work.actionable}
    band = sorted(bands, key=lambda b: b.within_days)[0]
    report = build_work_report("WRX1", work, band=band)
    assert report.jobs >= 1
    assert all(line.priority == band.label for line in report.lines_in)


def test_a_band_nobody_is_in_gives_an_empty_report() -> None:
    report = build_work_report("WRX1", a_list(), band=Priority.DEFERRED)
    assert report.jobs == 0
    assert report.total_cost.is_zero
    assert report.payback_years is None


def test_the_payback_text_reads_like_english() -> None:
    report = build_work_report("WRX1", a_list())
    assert all(
        line.payback_text.endswith("y") or line.payback_text in {"never", "at once"}
        for line in report.lines_in
    )


def test_the_band_counts_add_to_the_job_count() -> None:
    report = build_work_report("WRX1", a_list())
    assert sum(report.band_counts().values()) == report.jobs


def test_the_whole_list_pays_back(none_needed: None = None) -> None:
    report = build_work_report("WRX1", a_list())
    payback = report.payback_years
    assert payback is not None
    assert payback < 1.0
    assert "pays back in" in report.render()


def test_the_table_holds_one_line_per_job() -> None:
    report = build_work_report("WRX1", a_list())
    table = report.table()
    assert len(table) == report.jobs
    assert len(table.lines()) == report.jobs + 2


def test_the_json_shape_carries_the_lines_and_the_totals() -> None:
    report = build_work_report("WRX1", a_list(), Money.from_dollars("200.00"))
    payload = report.as_dict()
    assert payload["site"] == "WRX1"
    assert payload["jobs"] == 2
    assert payload["budget_cents"] == 20000
    assert isinstance(payload["lines"], list)
    assert set(payload["lines"][0]) >= {"tag", "priority", "cost_cents", "inside_budget"}
    assert payload["payback_years"] == pytest.approx(report.payback_years)
