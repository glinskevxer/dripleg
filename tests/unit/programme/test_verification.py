from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ValidationError
from dripleg.model.tags import TrapTag
from dripleg.programme.verification import (
    RepairOutcome,
    assess_repairs,
    cancelled_and_verified,
)
from dripleg.repair.recommend import Action, Recommendation
from dripleg.repair.workorder import WorkOrder
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money

RAISED = dt.date(2025, 4, 14)
BLOW = TrapCondition.BLOWING_THROUGH
OK = TrapCondition.OK


def a_job(tag: str) -> Recommendation:
    return Recommendation(
        tag=TrapTag.parse(tag),
        action=Action.REPAIR,
        reason="blowing through",
        parts=Money.from_dollars("64.40"),
        labour=Money.from_dollars("74.00"),
        permit=Money.zero(),
        annual_saving=Money.from_dollars("2613.18"),
    )


def a_finished_order(number: str, tag: str, completed: dt.date) -> WorkOrder:
    order = WorkOrder.raise_for(number, a_job(tag), on=RAISED, within_days=30)
    order.issue("A Frayne", RAISED)
    order.start(completed)
    order.complete(completed)
    return order


def test_a_repair_that_passes_next_time_held() -> None:
    order = a_finished_order("WO-1", "B12-MP-1", RAISED)
    history = {TrapTag.parse("B12-MP-1"): [(dt.date(2025, 10, 8), OK)]}
    report = assess_repairs([order], history)
    assert report.repairs == 1
    assert report.outcomes[0].held
    assert report.outcomes[0].outcome == "held"
    assert report.hold_rate == pytest.approx(1.0)


def test_a_repair_that_fails_next_time_came_back() -> None:
    order = a_finished_order("WO-1", "B12-MP-1", RAISED)
    history = {TrapTag.parse("B12-MP-1"): [(dt.date(2025, 10, 8), BLOW)]}
    report = assess_repairs([order], history)
    assert report.outcomes[0].came_back
    assert report.came_back_rate == pytest.approx(1.0)


def test_a_repair_nobody_has_read_since_is_unproven() -> None:
    order = a_finished_order("WO-1", "B12-MP-1", RAISED)
    report = assess_repairs([order], {})
    assert report.outcomes[0].is_unproven
    assert report.proven == 0
    assert report.hold_rate == 0.0
    assert report.outcomes[0].days_to_next_survey is None


def test_only_surveys_after_the_repair_count() -> None:
    order = a_finished_order("WO-1", "B12-MP-1", dt.date(2025, 6, 1))
    history = {
        TrapTag.parse("B12-MP-1"): [
            (dt.date(2025, 4, 8), BLOW),
            (dt.date(2025, 10, 8), OK),
        ]
    }
    report = assess_repairs([order], history)
    assert report.outcomes[0].next_surveyed_on == dt.date(2025, 10, 8)
    assert report.outcomes[0].held


def test_the_first_survey_after_the_repair_is_the_one_that_counts() -> None:
    order = a_finished_order("WO-1", "B12-MP-1", dt.date(2025, 6, 1))
    history = {
        TrapTag.parse("B12-MP-1"): [
            (dt.date(2025, 10, 8), BLOW),
            (dt.date(2026, 4, 8), OK),
        ]
    }
    assert assess_repairs([order], history).outcomes[0].came_back


def test_an_unfinished_order_is_not_assessed() -> None:
    order = WorkOrder.raise_for("WO-1", a_job("B12-MP-1"), on=RAISED, within_days=30)
    assert assess_repairs([order], {}).repairs == 0


def test_the_days_to_the_next_survey() -> None:
    order = a_finished_order("WO-1", "B12-MP-1", dt.date(2025, 6, 1))
    history = {TrapTag.parse("B12-MP-1"): [(dt.date(2025, 10, 8), OK)]}
    outcome = assess_repairs([order], history).outcomes[0]
    assert outcome.days_to_next_survey == 129
    assert assess_repairs([order], {}).outcomes[0].days_to_next_survey is None


def test_the_rates_are_over_what_has_been_proven() -> None:
    orders = [
        a_finished_order("WO-1", "B12-MP-1", RAISED),
        a_finished_order("WO-2", "B12-MP-2", RAISED),
        a_finished_order("WO-3", "B12-MP-3", RAISED),
    ]
    history = {
        TrapTag.parse("B12-MP-1"): [(dt.date(2025, 10, 8), OK)],
        TrapTag.parse("B12-MP-2"): [(dt.date(2025, 10, 8), BLOW)],
    }
    report = assess_repairs(orders, history)
    assert report.repairs == 3
    assert report.proven == 2
    assert report.hold_rate == pytest.approx(0.5)
    assert report.came_back_rate == pytest.approx(0.5)
    assert report.counts() == {"held": 1, "came back": 1, "unproven": 1}


def test_an_outcome_nobody_named_is_refused() -> None:
    with pytest.raises(ValidationError, match="is not an outcome"):
        assess_repairs([], {}).in_outcome("mostly fine")


def test_an_empty_report_has_no_rates() -> None:
    report = assess_repairs([], {})
    assert report.repairs == 0
    assert report.hold_rate == 0.0
    assert report.came_back_rate == 0.0


def test_cancelled_orders_are_pulled_out_separately() -> None:
    order = WorkOrder.raise_for("WO-1", a_job("B12-MP-1"), on=RAISED, within_days=30)
    order.cancel(RAISED, "the line came out")
    assert [o.number for o in cancelled_and_verified([order])] == ["WO-1"]
    assert cancelled_and_verified([a_finished_order("WO-2", "B12-MP-2", RAISED)]) == []


def test_printing_an_outcome_and_a_report() -> None:
    order = a_finished_order("WO-1", "B12-MP-1", RAISED)
    history = {TrapTag.parse("B12-MP-1"): [(dt.date(2025, 10, 8), OK)]}
    report = assess_repairs([order], history)
    assert str(report.outcomes[0]) == ("B12-MP-0001 repaired 2025-04-14, held at the next survey")
    assert str(assess_repairs([order], {}).outcomes[0]).endswith("not read since")
    assert str(report) == "1 repairs: 1 held, 0 came back, 0 unproven"


def test_an_outcome_can_be_built_by_hand() -> None:
    outcome = RepairOutcome(
        number="WO-1",
        tag=TrapTag.parse("B12-MP-1"),
        completed_on=RAISED,
        next_surveyed_on=None,
        next_condition=None,
    )
    assert outcome.is_unproven
    assert not outcome.held
    assert not outcome.came_back
