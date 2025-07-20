from __future__ import annotations

import datetime as dt

import pytest

from dripleg.errors import ConflictError, ValidationError
from dripleg.model.tags import TrapTag
from dripleg.repair.recommend import Action, Recommendation
from dripleg.repair.workorder import WorkOrder, WorkOrderState
from dripleg.units.money import Money

RAISED = dt.date(2025, 4, 14)
TAG = TrapTag.parse("B12-MP-0043")


def a_job(action: Action = Action.REPAIR) -> Recommendation:
    return Recommendation(
        tag=TAG,
        action=action,
        reason="the last visit read it blowing through",
        parts=Money.from_dollars("64.40"),
        labour=Money.from_dollars("74.00"),
        permit=Money.zero(),
        annual_saving=Money.from_dollars("2613.18"),
    )


def an_order(**overrides: object) -> WorkOrder:
    order = WorkOrder.raise_for("WO-4411", a_job(), on=RAISED, within_days=30)
    for name, value in overrides.items():
        setattr(order, name, value)
    return order


def test_an_order_is_raised_from_a_recommendation() -> None:
    order = an_order()
    assert order.number == "WO-4411"
    assert order.tag == TAG
    assert order.action is Action.REPAIR
    assert order.due_on == RAISED + dt.timedelta(days=30)
    assert order.estimated_cost == Money.from_dollars("138.40")
    assert order.state is WorkOrderState.RAISED
    assert order.is_open


def test_a_recommendation_that_is_not_work_raises_no_order() -> None:
    with pytest.raises(ValidationError, match="is not a work order"):
        WorkOrder.raise_for("WO-1", a_job(Action.MONITOR), on=RAISED, within_days=30)


def test_the_number_is_checked_and_normalised() -> None:
    order = WorkOrder.raise_for(" wo-4411 ", a_job(), on=RAISED, within_days=30)
    assert order.number == "WO-4411"
    with pytest.raises(ValidationError, match="not a work order number"):
        WorkOrder.raise_for("x", a_job(), on=RAISED, within_days=30)


def test_a_due_date_before_the_raised_date_is_refused() -> None:
    with pytest.raises(ValidationError, match="not due before it is raised"):
        WorkOrder(
            number="WO-1",
            tag=TAG,
            action=Action.REPAIR,
            raised_on=RAISED,
            due_on=RAISED - dt.timedelta(days=1),
            estimated_cost=Money.zero(),
        )


def test_a_negative_estimate_is_refused() -> None:
    with pytest.raises(ValidationError, match="estimate is not negative"):
        WorkOrder(
            number="WO-1",
            tag=TAG,
            action=Action.REPAIR,
            raised_on=RAISED,
            due_on=RAISED,
            estimated_cost=Money.from_cents(-1),
        )


def test_the_ordinary_run_through_to_verified() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED + dt.timedelta(days=1))
    order.start(RAISED + dt.timedelta(days=4))
    order.complete(RAISED + dt.timedelta(days=4), Money.from_dollars("151.20"))
    assert order.awaiting_verification
    order.verify(RAISED + dt.timedelta(days=18))
    assert order.state is WorkOrderState.VERIFIED
    assert not order.is_open
    assert order.assigned_to == "A Frayne"
    assert len(order.history) == 4


def test_done_is_not_the_end_state() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    order.complete(RAISED)
    assert order.is_open
    assert order.awaiting_verification


def test_a_job_cannot_skip_states() -> None:
    order = an_order()
    with pytest.raises(ConflictError, match="cannot go from raised to done"):
        order.complete(RAISED)
    order.issue("A Frayne", RAISED)
    with pytest.raises(ConflictError, match="cannot go from issued to done"):
        order.complete(RAISED)
    order.start(RAISED)
    order.complete(RAISED)
    with pytest.raises(ConflictError, match="cannot go from done to issued"):
        order.issue("A Frayne", RAISED)


def test_a_job_is_issued_to_somebody() -> None:
    with pytest.raises(ValidationError, match="issued to somebody"):
        an_order().issue("   ", RAISED)


def test_verification_needs_a_completion_date() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    order.complete(RAISED)
    order.completed_on = None
    with pytest.raises(ConflictError, match="no completion date"):
        order.verify(RAISED)


def test_a_verification_reading_comes_after_the_work() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    order.complete(RAISED + dt.timedelta(days=5))
    with pytest.raises(ValidationError, match="after the work"):
        order.verify(RAISED + dt.timedelta(days=2))


def test_a_failed_retest_reopens_the_job() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    order.complete(RAISED + dt.timedelta(days=2))
    order.reopen(RAISED + dt.timedelta(days=20), "still blowing on the retest")
    assert order.state is WorkOrderState.IN_PROGRESS
    assert order.completed_on is None
    assert "reopened" in order.history[-1]


def test_a_job_can_be_deferred_and_picked_back_up() -> None:
    order = an_order()
    later = RAISED + dt.timedelta(days=120)
    seen: list[WorkOrderState] = []
    order.defer(RAISED, later, "waiting for the shutdown")
    seen.append(order.state)
    assert order.due_on == later
    order.issue("A Frayne", later)
    seen.append(order.state)
    assert seen == [WorkOrderState.DEFERRED, WorkOrderState.ISSUED]


def test_a_job_cannot_be_deferred_backwards() -> None:
    with pytest.raises(ValidationError, match="deferred to a later date"):
        an_order().defer(RAISED, RAISED - dt.timedelta(days=1), "no")


def test_a_cancelled_job_goes_nowhere() -> None:
    order = an_order()
    order.cancel(RAISED, "the line came out")
    assert order.state is WorkOrderState.CANCELLED
    assert not order.is_open
    with pytest.raises(ConflictError, match="cannot go from cancelled"):
        order.issue("A Frayne", RAISED)


def test_a_verified_job_goes_nowhere_either() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    order.complete(RAISED)
    order.verify(RAISED + dt.timedelta(days=1))
    with pytest.raises(ConflictError, match="cannot go from verified"):
        order.reopen(RAISED + dt.timedelta(days=2), "no")


def test_overdue_is_only_for_open_jobs() -> None:
    order = an_order()
    late = RAISED + dt.timedelta(days=45)
    assert order.is_overdue_on(late)
    assert not order.is_overdue_on(RAISED + dt.timedelta(days=10))
    order.cancel(late, "abandoned")
    assert not order.is_overdue_on(late)


def test_days_open_stops_at_verification() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    order.complete(RAISED + dt.timedelta(days=3))
    order.verify(RAISED + dt.timedelta(days=10))
    assert order.days_open_on(RAISED + dt.timedelta(days=90)) == 10


def test_days_open_on_an_open_job_runs_to_today() -> None:
    assert an_order().days_open_on(RAISED + dt.timedelta(days=7)) == 7
    assert an_order().days_open_on(RAISED - dt.timedelta(days=7)) == 0


def test_the_cost_variance_needs_an_actual() -> None:
    order = an_order()
    assert order.variance is None
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    order.complete(RAISED, Money.from_dollars("151.20"))
    assert order.variance == Money.from_dollars("12.80")


def test_a_completion_before_the_raised_date_is_refused() -> None:
    order = an_order()
    order.issue("A Frayne", RAISED)
    order.start(RAISED)
    with pytest.raises(ValidationError, match="not finished before it is raised"):
        order.complete(RAISED - dt.timedelta(days=1))


def test_the_states_know_which_are_open_and_finished() -> None:
    assert WorkOrderState.RAISED.is_open
    assert not WorkOrderState.VERIFIED.is_open
    assert not WorkOrderState.CANCELLED.is_open
    assert WorkOrderState.DONE.work_is_finished
    assert WorkOrderState.VERIFIED.work_is_finished
    assert not WorkOrderState.IN_PROGRESS.work_is_finished


def test_printing_an_order() -> None:
    assert str(an_order()) == "WO-4411 B12-MP-0043 repair (raised)"
