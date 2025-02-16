"""A trap in a place, which is the record everything else hangs off.

The distinction that matters here is between the trap station and the trap.
The station is a spot on a pipe with a tag on it, and it stays there for
decades. The trap is a lump of iron that gets changed out every few years. A
survey reads the station, a work order changes the trap, and the reliability
report needs both, so an installation carries the tag, the model in it now, and
the day that model went in.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.attributes import Accessibility, Criticality, ServiceType
from dripleg.model.calendar import add_months
from dripleg.model.catalogue import TrapModel
from dripleg.model.header import DischargeDestination, SteamHeader
from dripleg.model.operating import OperatingProfile
from dripleg.model.tags import SiteCode, TrapTag

__all__ = ["TrapInstallation"]


@dataclass(frozen=True)
class TrapInstallation:
    """One trap station, and whatever is fitted to it now."""

    site: SiteCode
    tag: TrapTag
    header: SteamHeader
    model: TrapModel
    service: ServiceType
    accessibility: Accessibility
    criticality: Criticality
    profile: OperatingProfile
    installed_on: dt.date
    destination: DischargeDestination | None = None
    removed_on: dt.date | None = None
    strainer_fitted: bool = True
    isolation_valves: int = 2
    test_valve_fitted: bool = False
    insulated: bool = True
    interval_months_override: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.tag.area != self.header.area:
            raise ValidationError(
                f"tag {self.tag} is not in the same area as header {self.header.area}",
                field="tag",
            )
        if self.site != self.header.site:
            raise ValidationError("the trap and its header are at different sites", field="site")
        if self.removed_on is not None and self.removed_on < self.installed_on:
            raise ValidationError("a trap cannot come out before it went in", field="removed_on")
        if not 0 <= self.isolation_valves <= 2:
            raise ValidationError(
                "a station has none, one or two isolation valves",
                field="isolation_valves",
            )
        if (
            self.interval_months_override is not None
            and not 1 <= self.interval_months_override <= 60
        ):
            raise ValidationError(
                "a survey interval override runs from one month to five years",
                field="interval_months_override",
            )
        if not self.model.suits_pressure(self.header.operating_pressure):
            raise ValidationError(
                f"{self.model.code} is rated to {self.model.max_operating_pressure} "
                f"and the header runs at {self.header.operating_pressure}",
                field="model",
            )

    @property
    def discharge_destination(self) -> DischargeDestination:
        """The station's own destination if it has one, else the header's."""

        return self.destination if self.destination is not None else self.header.destination

    @property
    def key(self) -> tuple[str, str]:
        return (self.site.value, str(self.tag))

    @property
    def is_removed(self) -> bool:
        return self.removed_on is not None

    def is_in_service_on(self, day: dt.date) -> bool:
        if day < self.installed_on:
            return False
        return self.removed_on is None or day < self.removed_on

    def age_days_on(self, day: dt.date) -> int:
        """How long the fitted trap has been in on a given day."""

        if day < self.installed_on:
            raise ValidationError("that day is before the trap went in", field="day")
        end = min(day, self.removed_on) if self.removed_on is not None else day
        return (end - self.installed_on).days

    @property
    def survey_interval_months(self) -> int:
        if self.interval_months_override is not None:
            return self.interval_months_override
        return self.service.survey_interval_months

    def next_due_after(self, surveyed_on: dt.date) -> dt.date:
        return add_months(surveyed_on, self.survey_interval_months)

    @property
    def can_be_isolated(self) -> bool:
        """Whether the trap can be changed without shutting the header down."""

        return self.isolation_valves >= 1 and self.accessibility.can_be_done_running

    @property
    def loss_is_recovered(self) -> bool:
        return self.discharge_destination.condensate_is_recovered

    def replaced_with(self, model: TrapModel, on: dt.date) -> TrapInstallation:
        """The same station carrying a different trap from a given day."""

        if self.removed_on is not None:
            raise ValidationError("this station is out of service", field="removed_on")
        if on < self.installed_on:
            raise ValidationError("a replacement cannot predate what it replaces", field="on")
        return TrapInstallation(
            site=self.site,
            tag=self.tag,
            header=self.header,
            model=model,
            service=self.service,
            accessibility=self.accessibility,
            criticality=self.criticality,
            profile=self.profile,
            installed_on=on,
            destination=self.destination,
            strainer_fitted=self.strainer_fitted,
            isolation_valves=self.isolation_valves,
            test_valve_fitted=self.test_valve_fitted,
            insulated=self.insulated,
            interval_months_override=self.interval_months_override,
            note=self.note,
        )

    def retired_on(self, day: dt.date) -> TrapInstallation:
        if self.removed_on is not None:
            raise ValidationError("this station is already out of service", field="removed_on")
        return TrapInstallation(**{**self.__dict__, "removed_on": day})

    def __str__(self) -> str:
        return f"{self.tag} {self.service.label} on {self.header.name}"
