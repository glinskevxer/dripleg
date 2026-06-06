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
from dripleg.report.energy_report import EnergyReport, build_energy_report
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from tests.support.build import DAY, a_station, pipe, probe

BLOWING: dict[str, object] = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY: dict[str, object] = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}


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


def a_report() -> EnergyReport:
    return build_energy_report(
        a_loss_register([("B12-MP-1", BLOWING), ("B12-MP-2", HEALTHY), ("C3-MP-1", BLOWING)])
    )


def test_the_headline_is_fuel_and_carbon_not_money() -> None:
    report = a_report()
    assert "MMBtu of fuel" in report.headline
    assert "t CO2e a year on the natural gas factor" in report.headline
    assert "$" not in report.headline


def test_the_summary_carries_the_makeup_water_too() -> None:
    lines = "\n".join(a_report().summary_lines())
    assert "makeup water" in lines
    assert "factor          natural gas at 53.1 kg/MMBtu" in lines


def test_only_the_losing_traps_are_named() -> None:
    report = a_report()
    assert len(report.rows) == 2
    assert all(row[1] != "ok" for row in report.rows)


def test_the_traps_rank_by_fuel_not_by_money() -> None:
    report = a_report()
    burned = [float(row[3].replace(",", "")) for row in report.rows]
    assert burned == sorted(burned, reverse=True)


def test_the_top_can_be_cut_short() -> None:
    register = a_loss_register([("B12-MP-1", BLOWING), ("C3-MP-1", BLOWING)])
    assert len(build_energy_report(register, top=1).rows) == 1


def test_the_areas_add_up_to_the_total() -> None:
    report = a_report()
    total = sum(float(row[1].replace(",", "")) for row in report.by_area)
    assert total == pytest.approx(report.fuel.mmbtu, rel=0.01)


def test_a_register_that_lost_nothing_reports_zero() -> None:
    report = build_energy_report(a_loss_register([("B12-MP-2", HEALTHY)]))
    assert report.fuel.mmbtu == pytest.approx(0.0)
    assert report.tonnes_co2e == pytest.approx(0.0)
    assert report.rows == []
    assert report.factor == "natural gas"


def test_an_empty_register_has_no_factor() -> None:
    report = build_energy_report(a_loss_register([]))
    assert report.factor == "none"
    assert report.kg_per_mmbtu == 0.0
    assert "by area" in report.render()


def test_the_rendered_report_has_both_tables() -> None:
    rendered = a_report().render()
    assert "by trap" in rendered
    assert "by area" in rendered


def test_the_json_shape_carries_both_views() -> None:
    payload = a_report().as_dict()
    assert payload["factor"] == "natural gas"
    burned = payload["mmbtu"]
    assert isinstance(burned, float)
    assert burned > 0
    traps = payload["traps"]
    assert isinstance(traps, list)
    assert set(traps[0]) == {
        "tag",
        "condition",
        "pounds_per_year",
        "mmbtu_per_year",
        "tonnes_co2e",
    }
