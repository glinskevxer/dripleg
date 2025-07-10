from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest

from dripleg.diagnosis.batch import diagnose_survey
from dripleg.errors import ValidationError
from dripleg.loss.cost import CostBasis
from dripleg.loss.emissions import FACTORS
from dripleg.loss.energy import EnergyModel
from dripleg.loss.register import TrapLoss, build_loss_register
from dripleg.model.attributes import Accessibility
from dripleg.model.catalogue import TrapCatalogue, TrapModel
from dripleg.model.register import TrapRegister
from dripleg.model.tags import TrapTag
from dripleg.repair.recommend import Action, Recommendation, RepairBasis, recommend
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation
from dripleg.survey.survey import Survey
from dripleg.units.money import Money, Price
from tests.support.build import DAY, a_model, a_station, pipe, probe

BLOWING = {"ultrasonic": probe(70.0, 0), "temperature": pipe(345.0, 258.0)}
HEALTHY = {"ultrasonic": probe(32.0, 2), "temperature": pipe(350.0, 200.0)}
RESTRICTED = {"ultrasonic": probe(20.0), "temperature": pipe(300.0, 200.0)}
QUIET = {"ultrasonic": probe(4.0), "temperature": pipe(160.0, 130.0)}
FAST = {"ultrasonic": probe(40.0, 10), "temperature": pipe(350.0, 200.0)}


def a_row(readings: dict[str, object], **station: object) -> TrapLoss:
    trap = a_station(**station)
    register = TrapRegister([trap])
    survey = Survey("WRX1", "S2025-1", "Spring", "Vane", DAY - dt.timedelta(days=1))
    survey.record(
        Observation(
            tag=trap.tag,
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
    row = loss.find(trap.tag)
    assert row is not None
    return row


def test_the_basis_checks_itself() -> None:
    with pytest.raises(ValidationError, match="priced per hour"):
        RepairBasis(labour=Price.of("74.00", "day"))
    with pytest.raises(ValidationError, match="takes some time"):
        RepairBasis(labour=Price.of("74.00", "h"), base_hours=0.0)
    with pytest.raises(ValidationError, match="fraction of the trap price"):
        RepairBasis(labour=Price.of("74.00", "h"), kit_fraction=2.0)


def test_a_healthy_trap_is_left_alone() -> None:
    result = recommend(a_row(HEALTHY), RepairBasis.typical())
    assert result.action is Action.LEAVE
    assert result.cost.is_zero
    assert result.annual_saving.is_zero
    assert result.payback_years is None
    assert not result.action.is_work


def test_a_blowing_trap_is_repaired() -> None:
    result = recommend(a_row(BLOWING), RepairBasis.typical())
    assert result.action is Action.REPAIR
    assert result.parts.cents == pytest.approx(int(18400 * 0.35))
    assert result.labour == Money.from_dollars("74.00")
    assert result.annual_saving.cents > 0
    assert result.pays_back_inside_a_year


def test_a_discontinued_model_is_replaced_not_repaired() -> None:
    catalogue = TrapCatalogue([a_model(), _successor()])
    row = a_row(BLOWING, model=_discontinued())
    result = recommend(row, RepairBasis.typical(), catalogue)
    assert result.action is Action.REPLACE
    assert result.replacement is not None
    assert result.replacement.code == "TD75"
    assert result.parts == result.replacement.list_price


def test_a_plugged_trap_with_a_strainer_is_cleaned() -> None:
    result = recommend(a_row(RESTRICTED), RepairBasis.typical())
    assert result.action is Action.CLEAN
    assert result.parts.is_zero
    assert result.labour == Money.from_dollars("37.00")


def test_a_plugged_trap_without_a_strainer_is_repaired() -> None:
    result = recommend(a_row(RESTRICTED, strainer_fitted=False), RepairBasis.typical())
    assert result.action is Action.REPAIR


def test_a_cold_trap_is_repaired() -> None:
    result = recommend(a_row(QUIET), RepairBasis.typical())
    assert result.action is Action.REPAIR
    assert "failed closed" in result.reason


def test_a_fast_cycling_trap_is_resized() -> None:
    catalogue = TrapCatalogue([a_model()])
    result = recommend(a_row(FAST), RepairBasis.typical(), catalogue)
    assert result.action is Action.RESIZE
    assert result.replacement is not None
    assert "oversized" in result.reason


def test_access_multiplies_the_labour() -> None:
    easy = recommend(a_row(BLOWING), RepairBasis.typical())
    hard = recommend(
        a_row(BLOWING, accessibility=Accessibility.SCAFFOLD_REQUIRED), RepairBasis.typical()
    )
    assert hard.labour.cents == easy.labour.cents * 4
    assert hard.cost.cents > easy.cost.cents


def test_a_permit_job_carries_the_permit_cost() -> None:
    result = recommend(
        a_row(BLOWING, accessibility=Accessibility.CONFINED_SPACE), RepairBasis.typical()
    )
    assert result.permit == Money.from_dollars("120.00")
    assert result.cost == result.parts + result.labour + result.permit


def test_a_job_with_no_permit_carries_none() -> None:
    assert recommend(a_row(BLOWING), RepairBasis.typical()).permit.is_zero


def test_a_provisional_pass_is_monitored_rather_than_left() -> None:
    result = recommend(a_row({"ultrasonic": probe(32.0, 2)}), RepairBasis.typical())
    assert result.action is Action.MONITOR
    assert not result.action.is_work
    assert result.cost.is_zero


def test_a_trap_that_could_not_be_found_is_investigated() -> None:
    trap = a_station()
    register = TrapRegister([trap])
    survey = Survey("WRX1", "S2025-1", "Spring", "Vane", DAY - dt.timedelta(days=1))
    survey.record(
        Observation(
            tag=trap.tag,
            observed_on=DAY,
            technician="R Ellis",
            reported_condition=TrapCondition.NOT_FOUND,
        )
    )
    loss = build_loss_register(
        register,
        diagnose_survey(register, survey),
        EnergyModel.typical(),
        CostBasis.typical(),
        FACTORS["natural_gas"],
    )
    row = loss.find(trap.tag)
    assert row is not None
    result = recommend(row, RepairBasis.typical())
    assert result.action is Action.INVESTIGATE
    assert "not found" in result.reason


def test_a_recommendation_has_to_say_why() -> None:
    with pytest.raises(ValidationError, match="say why"):
        Recommendation(
            tag=TrapTag.parse("B12-MP-1"),
            action=Action.LEAVE,
            reason="  ",
            parts=Money.zero(),
            labour=Money.zero(),
            permit=Money.zero(),
            annual_saving=Money.zero(),
        )


def test_a_replacement_recommendation_has_to_name_a_trap() -> None:
    with pytest.raises(ValidationError, match="has to name a trap"):
        Recommendation(
            tag=TrapTag.parse("B12-MP-1"),
            action=Action.REPLACE,
            reason="worn out",
            parts=Money.from_dollars("184.00"),
            labour=Money.zero(),
            permit=Money.zero(),
            annual_saving=Money.zero(),
        )


def test_a_discontinued_model_with_no_successor_is_reported() -> None:
    row = a_row(BLOWING, model=_discontinued())
    with pytest.raises(ValidationError, match="nothing replaces it"):
        recommend(row, RepairBasis.typical(), TrapCatalogue([_discontinued()]))


def test_the_first_year_net_is_the_saving_less_the_cost() -> None:
    result = recommend(a_row(BLOWING), RepairBasis.typical())
    assert result.net_first_year == result.annual_saving - result.cost
    assert result.net_first_year.cents > 0


def test_printing_a_recommendation() -> None:
    work = recommend(a_row(BLOWING), RepairBasis.typical())
    assert str(work).startswith("B12-MP-0043 repair for $")
    assert "pays back in" in str(work)
    left = recommend(a_row(HEALTHY), RepairBasis.typical())
    assert str(left) == "B12-MP-0043 leave: passing on the last visit"


def test_the_action_labels_and_flags() -> None:
    assert Action.CONFIRM_ISOLATION.label == "confirm isolation"
    assert Action.RESIZE.needs_a_trap
    assert not Action.REPAIR.needs_a_trap
    assert not Action.MONITOR.is_work


def _discontinued() -> TrapModel:
    return replace(a_model(), discontinued=True, replaced_by="TD75")


def _successor() -> TrapModel:
    return replace(a_model(), code="TD75", list_price=Money.from_dollars("96.50"))
