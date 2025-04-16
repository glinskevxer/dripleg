"""A survey: one pass over some part of a plant, and what it found.

The number that gets argued over at the closing meeting is the failure rate,
and the argument is almost always about the denominator. Failures over stations
on the register flatters nobody. Failures over stations actually assessed
flatters the contractor, because every trap they could not find drops out of
the bottom. Both are reported here, separately, with the gap between them named
as what it is.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ConflictError, ValidationError
from dripleg.model.calendar import DateRange
from dripleg.model.register import TrapRegister
from dripleg.model.tags import SiteCode, TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.observation import Observation

__all__ = ["Coverage", "Survey"]


@dataclass(frozen=True)
class Coverage:
    """How much of the population this survey actually got a look at."""

    on_register: int
    observed: int
    assessed: int
    not_found: int
    inaccessible: int

    @property
    def not_visited(self) -> int:
        return self.on_register - self.observed

    @property
    def assessed_fraction(self) -> float:
        if self.on_register == 0:
            return 0.0
        return self.assessed / self.on_register

    @property
    def visited_fraction(self) -> float:
        if self.on_register == 0:
            return 0.0
        return self.observed / self.on_register

    @property
    def is_complete(self) -> bool:
        return self.on_register > 0 and self.assessed == self.on_register

    def __str__(self) -> str:
        return (
            f"{self.assessed} of {self.on_register} assessed "
            f"({self.assessed_fraction * 100:.1f}%), {self.not_visited} not visited"
        )


class Survey:
    """One pass over a plant, holding the observations it produced."""

    def __init__(
        self,
        site: SiteCode | str,
        reference: str,
        name: str,
        contractor: str,
        started_on: dt.date,
        finished_on: dt.date | None = None,
    ) -> None:
        self.site = site if isinstance(site, SiteCode) else SiteCode.parse(site)
        cleaned = reference.strip().upper()
        if not cleaned:
            raise ValidationError("a survey needs a reference", field="reference")
        self.reference = cleaned
        squeezed = " ".join(name.split())
        if not squeezed:
            raise ValidationError("a survey needs a name", field="name")
        self.name = squeezed
        who = " ".join(contractor.split())
        if not who:
            raise ValidationError("a survey needs a contractor", field="contractor")
        self.contractor = who
        if finished_on is not None and finished_on < started_on:
            raise ValidationError("a survey cannot end before it starts", field="finished_on")
        self.started_on = started_on
        self.finished_on = finished_on
        self._observations: dict[TrapTag, Observation] = {}

    @property
    def is_closed(self) -> bool:
        return self.finished_on is not None

    @property
    def window(self) -> DateRange:
        end = self.finished_on if self.finished_on is not None else self.last_observed_on
        if end is None:
            end = self.started_on
        return DateRange(self.started_on, end + dt.timedelta(days=1))

    @property
    def last_observed_on(self) -> dt.date | None:
        if not self._observations:
            return None
        return max(o.observed_on for o in self._observations.values())

    def record(self, observation: Observation) -> None:
        if self.is_closed:
            raise ConflictError(f"survey {self.reference} is closed")
        if observation.tag in self._observations:
            raise ConflictError(f"{observation.tag} has already been read on this survey")
        if observation.observed_on < self.started_on:
            raise ValidationError(
                f"{observation.observed_on} is before the survey started",
                field="observed_on",
            )
        self._observations[observation.tag] = observation

    def amend(self, observation: Observation) -> None:
        """Replace a reading, which is what a return visit produces."""

        if observation.tag not in self._observations:
            raise ConflictError(f"{observation.tag} has not been read on this survey")
        self._observations[observation.tag] = observation

    def close(self, on: dt.date) -> None:
        if self.is_closed:
            raise ConflictError(f"survey {self.reference} is already closed")
        last = self.last_observed_on
        if last is not None and on < last:
            raise ValidationError("a survey cannot close before its last reading", field="on")
        if on < self.started_on:
            raise ValidationError("a survey cannot close before it starts", field="on")
        self.finished_on = on

    def __len__(self) -> int:
        return len(self._observations)

    def __contains__(self, tag: object) -> bool:
        if isinstance(tag, str):
            return TrapTag.parse(tag) in self._observations
        return tag in self._observations

    @property
    def observations(self) -> list[Observation]:
        return [self._observations[tag] for tag in sorted(self._observations)]

    def find(self, tag: TrapTag | str) -> Observation | None:
        wanted = tag if isinstance(tag, TrapTag) else TrapTag.parse(tag)
        return self._observations.get(wanted)

    def condition_counts(self) -> dict[TrapCondition, int]:
        counts: dict[TrapCondition, int] = {}
        for observation in self._observations.values():
            counts[observation.reported_condition] = (
                counts.get(observation.reported_condition, 0) + 1
            )
        return dict(sorted(counts.items(), key=lambda pair: pair[0].rank))

    def failures(self) -> list[Observation]:
        return [o for o in self.observations if o.reported_condition.is_failure]

    def assessed(self) -> list[Observation]:
        return [o for o in self.observations if o.reported_condition.was_assessed]

    def coverage(self, register: TrapRegister) -> Coverage:
        on_register = len(register.in_service_on(self.started_on))
        observed = 0
        assessed = 0
        not_found = 0
        inaccessible = 0
        for observation in self._observations.values():
            if register.find(observation.tag) is None:
                continue
            observed += 1
            if observation.reported_condition is TrapCondition.NOT_FOUND:
                not_found += 1
            elif observation.reported_condition is TrapCondition.INACCESSIBLE:
                inaccessible += 1
            else:
                assessed += 1
        return Coverage(
            on_register=on_register,
            observed=observed,
            assessed=assessed,
            not_found=not_found,
            inaccessible=inaccessible,
        )

    def failure_rate(self, *, over_assessed: bool = True) -> float:
        """Failures over what was assessed, or over everything read."""

        denominator = len(self.assessed()) if over_assessed else len(self._observations)
        if denominator == 0:
            return 0.0
        return len(self.failures()) / denominator

    def observed_but_not_on_register(self, register: TrapRegister) -> list[TrapTag]:
        """Traps the technician found that nobody had written down."""

        return [tag for tag in sorted(self._observations) if register.find(tag) is None]

    def __str__(self) -> str:
        state = "closed" if self.is_closed else "open"
        return f"{self.reference} {self.name} ({len(self)} readings, {state})"
