"""Turning a finding into a job, costed the way the job actually costs.

The costing is where most trap survey reports quietly lose their audience. A
report that prices every repair at the list price of a trap plus an hour of
labour produces a payback list that the maintenance planner knows is wrong
before the meeting starts, because half those traps are up a ladder inside a
permit area and one of them needs the machine down.

So the cost here is parts plus labour times the access multiplier plus the
permit, and the access grade is on the register precisely so it can be used
here. The number gets bigger and the report gets believed.

The action is decided ahead of the cost, from the condition and the state of
what is fitted. A trap that failed once gets repaired. A trap on a discontinued
model, or one that has failed before, gets replaced, because the second repair
on the same station costs more than the trap did.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from dripleg.errors import ValidationError
from dripleg.loss.register import TrapLoss
from dripleg.model.catalogue import TrapCatalogue, TrapModel
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.units.money import Money, Price

__all__ = [
    "Action",
    "Recommendation",
    "RepairBasis",
    "recommend",
]


class Action(Enum):
    LEAVE = "leave"
    MONITOR = "monitor"
    CLEAN = "clean"
    REPAIR = "repair"
    REPLACE = "replace"
    RESIZE = "resize"
    INVESTIGATE = "investigate"
    CONFIRM_ISOLATION = "confirm_isolation"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def is_work(self) -> bool:
        """Whether this action puts a job on the maintenance list."""

        return self in {
            Action.CLEAN,
            Action.REPAIR,
            Action.REPLACE,
            Action.RESIZE,
        }

    @property
    def needs_a_trap(self) -> bool:
        return self in {Action.REPLACE, Action.RESIZE}


@dataclass(frozen=True)
class RepairBasis:
    """What a job costs before the access grade is applied."""

    labour: Price
    base_hours: float = 1.0
    kit_fraction: float = 0.35
    clean_hours: float = 0.5
    permit_cost: Money = Money.zero()

    def __post_init__(self) -> None:
        if "h" not in self.labour.unit.lower():
            raise ValidationError("labour is priced per hour", field="labour")
        if self.base_hours <= 0 or self.clean_hours <= 0:
            raise ValidationError("a job takes some time", field="base_hours")
        if not 0.0 < self.kit_fraction <= 1.0:
            raise ValidationError(
                "a repair kit is a fraction of the trap price", field="kit_fraction"
            )

    @classmethod
    def typical(cls) -> RepairBasis:
        return cls(labour=Price.of("74.00", "h"), permit_cost=Money.from_dollars("120.00"))

    def labour_cost(self, hours: float, multiplier: float) -> Money:
        return self.labour.times(Decimal(str(hours * multiplier)))


@dataclass(frozen=True)
class Recommendation:
    """One job: what to do, what it costs, and what it saves."""

    tag: TrapTag
    action: Action
    reason: str
    parts: Money
    labour: Money
    permit: Money
    annual_saving: Money
    replacement: TrapModel | None = None

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValidationError("a recommendation has to say why", field="reason")
        if self.action.needs_a_trap and self.replacement is None:
            raise ValidationError(
                f"a {self.action.label} recommendation has to name a trap",
                field="replacement",
            )

    @property
    def cost(self) -> Money:
        return self.parts + self.labour + self.permit

    @property
    def payback_years(self) -> float | None:
        return self.cost.payback_years(self.annual_saving)

    @property
    def pays_back_inside_a_year(self) -> bool:
        payback = self.payback_years
        return payback is not None and payback <= 1.0

    @property
    def net_first_year(self) -> Money:
        return self.annual_saving - self.cost

    def __str__(self) -> str:
        if not self.action.is_work:
            return f"{self.tag} {self.action.label}: {self.reason}"
        payback = self.payback_years
        if payback is None:
            return f"{self.tag} {self.action.label} for {self.cost}, no saving"
        return f"{self.tag} {self.action.label} for {self.cost}, pays back in {payback:.1f} y"


def _choose(row: TrapLoss) -> tuple[Action, str]:
    condition = row.diagnosis.condition
    station = row.station
    if not condition.was_assessed:
        return Action.INVESTIGATE, f"the trap was {condition.label} on the last visit"
    if condition is TrapCondition.OUT_OF_SERVICE:
        return Action.CONFIRM_ISOLATION, "the leg read dead, so check it is meant to be"
    if condition is TrapCondition.PLUGGED and station.strainer_fitted:
        return Action.CLEAN, "the strainer ahead of it is restricting the trap"
    if condition is TrapCondition.RAPID_CYCLING:
        return Action.RESIZE, "cycling far faster than the principle should, so it is oversized"
    if condition.is_failure:
        if station.model.discontinued:
            return Action.REPLACE, f"{station.model.code} is out of production"
        return Action.REPAIR, f"the last visit read it {condition.label}"
    if row.diagnosis.is_provisional:
        return Action.MONITOR, "the verdict rests on one method, so read it again"
    return Action.LEAVE, "passing on the last visit"


def recommend(
    row: TrapLoss,
    basis: RepairBasis,
    catalogue: TrapCatalogue | None = None,
) -> Recommendation:
    """What to do about one row of the loss register."""

    action, reason = _choose(row)
    station = row.station
    multiplier = station.accessibility.labour_multiplier
    permit = basis.permit_cost if station.accessibility.needs_a_permit else Money.zero()
    replacement: TrapModel | None = None
    if action is Action.CLEAN:
        parts = Money.zero()
        labour = basis.labour_cost(basis.clean_hours, multiplier)
    elif action is Action.REPAIR:
        parts = station.model.list_price.scaled(basis.kit_fraction)
        labour = basis.labour_cost(basis.base_hours, multiplier)
    elif action.needs_a_trap:
        replacement = _replacement_for(row, catalogue)
        parts = replacement.list_price
        labour = basis.labour_cost(basis.base_hours, multiplier)
    else:
        parts = Money.zero()
        labour = Money.zero()
        permit = Money.zero()
    saving = row.annual_cost if action.is_work else Money.zero()
    return Recommendation(
        tag=station.tag,
        action=action,
        reason=reason,
        parts=parts,
        labour=labour,
        permit=permit,
        annual_saving=saving,
        replacement=replacement,
    )


def _replacement_for(row: TrapLoss, catalogue: TrapCatalogue | None) -> TrapModel:
    """The cheapest current model that suits the header, or what is fitted."""

    if catalogue is not None:
        for candidate in catalogue.orderable_for(row.station.header):
            if candidate.principle is row.station.model.principle:
                return candidate
        successor = catalogue.successor_of(row.station.model)
        if successor is not None:
            return successor
    if row.station.model.discontinued:
        raise ValidationError(
            f"{row.station.model.code} is out of production and nothing replaces it",
            field="replacement",
        )
    return row.station.model
