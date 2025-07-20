"""Work orders, and the one transition that most trap programmes leave out.

A trap survey that ends at a repair list is a survey that gets repeated next
year with the same traps on it. The step everybody skips is verification: going
back after the job, reading the trap again, and recording that it is now fixed.
Without it the saving is a claim, and the second year's report cannot tell a
repaired trap from one that was never touched.

So `done` is not the end state here. `verified` is, and getting there needs a
reading taken after the completion date. A work order sitting in `done` for
three months is itself a finding.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from enum import Enum

from dripleg.errors import ConflictError, ValidationError
from dripleg.model.tags import TrapTag
from dripleg.repair.recommend import Action, Recommendation
from dripleg.units.money import Money

__all__ = ["WorkOrder", "WorkOrderState"]

_NUMBER = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,19}$")


class WorkOrderState(Enum):
    RAISED = "raised"
    ISSUED = "issued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    VERIFIED = "verified"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def is_open(self) -> bool:
        return self not in {
            WorkOrderState.VERIFIED,
            WorkOrderState.CANCELLED,
        }

    @property
    def work_is_finished(self) -> bool:
        return self in {WorkOrderState.DONE, WorkOrderState.VERIFIED}


_ALLOWED: dict[WorkOrderState, frozenset[WorkOrderState]] = {
    WorkOrderState.RAISED: frozenset(
        {WorkOrderState.ISSUED, WorkOrderState.DEFERRED, WorkOrderState.CANCELLED}
    ),
    WorkOrderState.ISSUED: frozenset(
        {WorkOrderState.IN_PROGRESS, WorkOrderState.DEFERRED, WorkOrderState.CANCELLED}
    ),
    WorkOrderState.IN_PROGRESS: frozenset({WorkOrderState.DONE, WorkOrderState.CANCELLED}),
    WorkOrderState.DONE: frozenset({WorkOrderState.VERIFIED, WorkOrderState.IN_PROGRESS}),
    WorkOrderState.DEFERRED: frozenset({WorkOrderState.ISSUED, WorkOrderState.CANCELLED}),
    WorkOrderState.VERIFIED: frozenset(),
    WorkOrderState.CANCELLED: frozenset(),
}


@dataclass
class WorkOrder:
    """One job on one trap, from raised to verified."""

    number: str
    tag: TrapTag
    action: Action
    raised_on: dt.date
    due_on: dt.date
    estimated_cost: Money
    state: WorkOrderState = WorkOrderState.RAISED
    assigned_to: str | None = None
    started_on: dt.date | None = None
    completed_on: dt.date | None = None
    verified_on: dt.date | None = None
    actual_cost: Money | None = None
    history: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        cleaned = self.number.strip().upper()
        if not _NUMBER.match(cleaned):
            raise ValidationError(f"{self.number!r} is not a work order number", field="number")
        self.number = cleaned
        if self.due_on < self.raised_on:
            raise ValidationError("a job is not due before it is raised", field="due_on")
        if self.estimated_cost.cents < 0:
            raise ValidationError("an estimate is not negative", field="estimated_cost")

    @classmethod
    def raise_for(
        cls,
        number: str,
        job: Recommendation,
        *,
        on: dt.date,
        within_days: int,
    ) -> WorkOrder:
        if not job.action.is_work:
            raise ValidationError(
                f"a {job.action.label} recommendation is not a work order",
                field="action",
            )
        return cls(
            number=number,
            tag=job.tag,
            action=job.action,
            raised_on=on,
            due_on=on + dt.timedelta(days=within_days),
            estimated_cost=job.cost,
        )

    def _move(self, to: WorkOrderState, on: dt.date, note: str) -> None:
        if to not in _ALLOWED[self.state]:
            raise ConflictError(f"{self.number} cannot go from {self.state.label} to {to.label}")
        self.history.append(f"{on} {self.state.label} to {to.label}: {note}")
        self.state = to

    def issue(self, to: str, on: dt.date) -> None:
        who = " ".join(to.split())
        if not who:
            raise ValidationError("a job is issued to somebody", field="assigned_to")
        self._move(WorkOrderState.ISSUED, on, f"issued to {who}")
        self.assigned_to = who

    def start(self, on: dt.date) -> None:
        self._move(WorkOrderState.IN_PROGRESS, on, "work started")
        self.started_on = on

    def complete(self, on: dt.date, cost: Money | None = None) -> None:
        if on < self.raised_on:
            raise ValidationError("a job is not finished before it is raised", field="on")
        self._move(WorkOrderState.DONE, on, "work finished")
        self.completed_on = on
        if cost is not None:
            self.actual_cost = cost

    def verify(self, on: dt.date) -> None:
        """Close the job on a reading taken after the work."""

        if self.completed_on is None:
            raise ConflictError(f"{self.number} has no completion date to verify against")
        if on < self.completed_on:
            raise ValidationError(
                "a verification reading comes after the work, not before", field="on"
            )
        self._move(WorkOrderState.VERIFIED, on, "verified on a retest")
        self.verified_on = on

    def reopen(self, on: dt.date, reason: str) -> None:
        """A retest that failed sends the job back to the crew."""

        self._move(WorkOrderState.IN_PROGRESS, on, f"reopened: {reason}")
        self.completed_on = None

    def defer(self, on: dt.date, until: dt.date, reason: str) -> None:
        if until < on:
            raise ValidationError("a job is deferred to a later date", field="until")
        self._move(WorkOrderState.DEFERRED, on, f"deferred to {until}: {reason}")
        self.due_on = until

    def cancel(self, on: dt.date, reason: str) -> None:
        self._move(WorkOrderState.CANCELLED, on, f"cancelled: {reason}")

    @property
    def is_open(self) -> bool:
        return self.state.is_open

    @property
    def awaiting_verification(self) -> bool:
        return self.state is WorkOrderState.DONE

    def is_overdue_on(self, day: dt.date) -> bool:
        return self.is_open and day > self.due_on

    def days_open_on(self, day: dt.date) -> int:
        end = self.verified_on if self.verified_on is not None else day
        return max((end - self.raised_on).days, 0)

    @property
    def variance(self) -> Money | None:
        if self.actual_cost is None:
            return None
        return self.actual_cost - self.estimated_cost

    def __str__(self) -> str:
        return f"{self.number} {self.tag} {self.action.label} ({self.state.label})"
