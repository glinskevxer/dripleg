from __future__ import annotations

import datetime as dt

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import LossRegister, build_loss_register
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.report.loss_report import LossReport, build_loss_report
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from tests.support.build import DAY, a_station, pipe, probe

BLOWING = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}


def a_loss_register(rows: list[tuple[str, dict[str, object]]]) -> LossRegister:
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
    return build_loss_register(
        register,
        diagnose_survey(register, survey),
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )


def a_report() -> LossReport:
    return build_loss_report(
        a_loss_register(
            [
                ("B12-MP-1", BLOWING),
                ("B12-MP-2", HEALTHY),
                ("C3-MP-1", BLOWING),
            ]
        )
    )


def test_the_headline_is_the_two_numbers_people_quote() -> None:
    report = a_report()
    assert report.headline.startswith("S2025-1: 2 of 3 traps losing $")
    assert report.loss_rate == pytest.approx(2 / 3)


def test_the_summary_carries_steam_fuel_and_carbon() -> None:
    lines = "\n".join(a_report().summary_lines())
    assert "traps            3" in lines
    assert "lb/h" in lines
    assert "MMBtu a year" in lines
    assert "t CO2e a year" in lines


def test_the_top_table_holds_only_the_losers() -> None:
    report = a_report()
    assert len(report.top) == 2
    assert all("ok" not in row[1] for row in report.top)
    assert len(report.top_table()) == 2


def test_the_top_table_can_be_cut_short() -> None:
    register = a_loss_register([("B12-MP-1", BLOWING), ("C3-MP-1", BLOWING)])
    assert len(build_loss_report(register, top=1).top) == 1


def test_the_area_shares_add_to_one() -> None:
    report = a_report()
    shares = [float(row[2].rstrip("%")) for row in report.by_area]
    assert sum(shares) == pytest.approx(100.0, abs=0.2)
    assert [row[0] for row in report.by_area] == ["B12", "C3"]


def test_the_condition_shares_lead_with_the_worst() -> None:
    report = a_report()
    assert report.by_condition[0][0] == "blowing through"
    assert report.by_condition[-1][0] == "ok"
    assert report.by_condition[-1][2] == "0.0%"


def test_a_register_that_lost_nothing_shares_out_as_zero() -> None:
    report = build_loss_report(a_loss_register([("B12-MP-2", HEALTHY)]))
    assert report.total_cost.is_zero
    assert report.loss_rate == 0.0
    assert report.by_area[0][2] == "0.0%"


def test_an_empty_register_still_renders() -> None:
    report = build_loss_report(a_loss_register([]))
    assert report.traps == 0
    assert report.loss_rate == 0.0
    assert report.top == []
    assert "by area" in report.render()


def test_the_rendered_report_has_all_three_tables() -> None:
    rendered = a_report().render()
    assert "the 2 dearest traps" in rendered
    assert "by area" in rendered
    assert "by condition" in rendered
    assert rendered.splitlines()[0] == a_report().headline


def test_the_json_shape_matches_the_text() -> None:
    payload = a_report().as_dict()
    assert payload["reference"] == "S2025-1"
    assert payload["traps"] == 3
    assert payload["losing"] == 2
    assert payload["annual_cost_cents"] == a_report().total_cost.cents
    assert isinstance(payload["top"], list)
    assert len(payload["top"]) == 2
    assert set(payload["top"][0]) == {"tag", "condition", "pounds_per_hour", "annual"}


def test_the_numbers_in_json_are_floats_not_money_objects() -> None:
    payload = a_report().as_dict()
    flow = payload["pounds_per_hour"]
    carbon = payload["tonnes_co2e"]
    assert isinstance(flow, float)
    assert isinstance(carbon, float)
    assert flow > 0
    assert carbon > 0
