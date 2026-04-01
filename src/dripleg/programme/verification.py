"""Did the repairs hold, which is the question that closes the loop.

A work order marked verified means somebody went back and read the trap. It
does not mean the trap was fixed, and the difference matters: a crew that
verifies on the same day it repairs is reading a trap that has not been through
a start up yet, and a proportion of those come back.

So this looks at what the trap was found to be at the *next* survey after the
repair, not at the retest, and reports three things:

- held: repaired, and passing at the next survey
- came back: repaired, and failing again at the next survey
- unproven: repaired, and not read since

The came back rate is the number that tells a plant whether it is buying
repairs or buying visits.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.tags import TrapTag
from dripleg.repair.workorder import WorkOrder, WorkOrderState
from dripleg.survey.condition import TrapCondition

__all__ = ["RepairOutcome", "VerificationReport", "assess_repairs"]


@dataclass(frozen=True)
class RepairOutcome:
    """One finished repair, and what the next survey made of it."""

    number: str
    tag: TrapTag
    completed_on: dt.date
    next_surveyed_on: dt.date | None
    next_condition: TrapCondition | None

    @property
    def is_unproven(self) -> bool:
        return self.next_condition is None

    @property
    def held(self) -> bool:
        return self.next_condition is not None and not self.next_condition.is_failure

    @property
    def came_back(self) -> bool:
        return self.next_condition is not None and self.next_condition.is_failure

    @property
    def days_to_next_survey(self) -> int | None:
        if self.next_surveyed_on is None:
            return None
        return (self.next_surveyed_on - self.completed_on).days

    @property
    def outcome(self) -> str:
        if self.is_unproven:
            return "unproven"
        return "held" if self.held else "came back"

    def __str__(self) -> str:
        if self.is_unproven:
            return f"{self.tag} repaired {self.completed_on}, not read since"
        return f"{self.tag} repaired {self.completed_on}, {self.outcome} at the next survey"


@dataclass(frozen=True)
class VerificationReport:
    """Every finished repair, and whether it held."""

    outcomes: list[RepairOutcome]

    @property
    def repairs(self) -> int:
        return len(self.outcomes)

    def in_outcome(self, outcome: str) -> list[RepairOutcome]:
        known = {"held", "came back", "unproven"}
        if outcome not in known:
            raise ValidationError(
                f"{outcome!r} is not an outcome, expected one of: {', '.join(sorted(known))}",
                field="outcome",
            )
        return [row for row in self.outcomes if row.outcome == outcome]

    @property
    def proven(self) -> int:
        return self.repairs - len(self.in_outcome("unproven"))

    @property
    def hold_rate(self) -> float:
        if self.proven == 0:
            return 0.0
        return len(self.in_outcome("held")) / self.proven

    @property
    def came_back_rate(self) -> float:
        if self.proven == 0:
            return 0.0
        return len(self.in_outcome("came back")) / self.proven

    def counts(self) -> dict[str, int]:
        return {name: len(self.in_outcome(name)) for name in ("held", "came back", "unproven")}

    def __str__(self) -> str:
        counts = self.counts()
        return (
            f"{self.repairs} repairs: {counts['held']} held, "
            f"{counts['came back']} came back, {counts['unproven']} unproven"
        )


def assess_repairs(
    orders: list[WorkOrder],
    history: dict[TrapTag, list[tuple[dt.date, TrapCondition]]],
) -> VerificationReport:
    """Hold each finished repair against the next survey that read the trap."""

    outcomes: list[RepairOutcome] = []
    for order in orders:
        if not order.state.work_is_finished or order.completed_on is None:
            continue
        later = [
            (surveyed_on, condition)
            for surveyed_on, condition in sorted(history.get(order.tag, []))
            if surveyed_on > order.completed_on
        ]
        first = later[0] if later else None
        outcomes.append(
            RepairOutcome(
                number=order.number,
                tag=order.tag,
                completed_on=order.completed_on,
                next_surveyed_on=None if first is None else first[0],
                next_condition=None if first is None else first[1],
            )
        )
    return VerificationReport(
        outcomes=sorted(outcomes, key=lambda row: (row.completed_on, str(row.tag)))
    )


def cancelled_and_verified(orders: list[WorkOrder]) -> list[WorkOrder]:
    """Orders that were closed without the work ever being done.

    A programme with a lot of these is not a programme with a low failure rate,
    it is a programme whose work list gets tidied rather than worked.
    """

    return [order for order in orders if order.state is WorkOrderState.CANCELLED]
