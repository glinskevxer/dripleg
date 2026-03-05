"""Everything a rule needs about one trap on one visit, worked out once.

Every rule wants the same handful of derived numbers: what pressure the header
was actually at, what saturation temperature that implies, how far under it the
inlet pipe was running, what the trap is supposed to behave like. Working those
out inside each rule means the saturation table gets read eleven times per trap
and, worse, means two rules can disagree about what pressure they were talking
about.

So it is worked out once, here, and handed to the rules read only.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import cached_property

from dripleg.errors import ValidationError
from dripleg.model.installation import TrapInstallation
from dripleg.model.principles import PrincipleProfile
from dripleg.steam.saturated import at_pressure
from dripleg.survey.observation import Observation
from dripleg.survey.readings import TemperatureReading, UltrasonicReading
from dripleg.thresholds import (
    CRITICAL_BACK_PRESSURE_RATIO,
    PRESSURE_DISAGREEMENT,
)
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature, TemperatureDelta

__all__ = ["DiagnosisContext"]


@dataclass(frozen=True)
class DiagnosisContext:
    """One trap, one reading, and the arithmetic that follows from both."""

    station: TrapInstallation
    observation: Observation

    def __post_init__(self) -> None:
        if self.station.tag != self.observation.tag:
            raise ValidationError(
                f"reading is for {self.observation.tag} and the station is {self.station.tag}",
                field="tag",
            )
        if not self.station.is_in_service_on(self.observation.observed_on):
            raise ValidationError(
                f"{self.station.tag} was not in service on {self.observation.observed_on}",
                field="observed_on",
            )

    @property
    def observed_on(self) -> dt.date:
        return self.observation.observed_on

    @property
    def principle(self) -> PrincipleProfile:
        return self.station.model.principle.profile

    @cached_property
    def pressure(self) -> Pressure:
        """What the header was at, preferring what the technician measured."""

        return self.observation.pressure_or(self.station.header.operating_pressure)

    @cached_property
    def saturation_temperature(self) -> Temperature:
        return at_pressure(self.pressure).temperature

    @property
    def discharge_pressure(self) -> Pressure:
        return self.station.header.discharge_pressure

    @property
    def back_pressure_ratio(self) -> float:
        return self.discharge_pressure.ratio_to(self.pressure)

    @property
    def is_choked(self) -> bool:
        return self.back_pressure_ratio <= CRITICAL_BACK_PRESSURE_RATIO

    @property
    def sound(self) -> UltrasonicReading | None:
        return self.observation.ultrasonic

    @property
    def heat(self) -> TemperatureReading | None:
        return self.observation.temperature

    @property
    def has_sound(self) -> bool:
        return self.observation.ultrasonic is not None

    @property
    def has_heat(self) -> bool:
        return self.observation.temperature is not None

    @property
    def cycles_per_minute(self) -> float | None:
        return self.observation.cycles_per_minute

    @cached_property
    def subcooling(self) -> TemperatureDelta | None:
        """How far below saturation the inlet pipe was, or None if not measured."""

        if self.heat is None:
            return None
        return self.heat.subcooling_below(self.pressure)

    @property
    def differential(self) -> TemperatureDelta | None:
        return None if self.heat is None else self.heat.differential

    @property
    def subcooling_is_normal(self) -> bool | None:
        """Whether the inlet reading sits in the band this principle works in."""

        gap = self.subcooling
        if gap is None:
            return None
        return self.principle.subcooling_is_normal(max(gap.fahrenheit, 0.0))

    @property
    def cycle_rate_is_normal(self) -> bool | None:
        rate = self.cycles_per_minute
        if rate is None:
            return None
        return self.principle.cycle_rate_is_normal(rate)

    @property
    def pressure_was_measured(self) -> bool:
        return self.observation.measured_pressure is not None

    @property
    def pressure_disagrees_with_register(self) -> bool:
        """Whether the measured pressure is far off what the register says.

        More than a fifth out means either the register is stale or the gauge
        is wrong, and both are worth saying out loud before anything is
        concluded from the number.
        """

        if not self.pressure_was_measured:
            return False
        register = self.station.header.operating_pressure.psia
        if register <= 0:
            return False
        return abs(self.pressure.psia - register) / register > PRESSURE_DISAGREEMENT

    def __str__(self) -> str:
        return f"{self.station.tag} on {self.observed_on} at {self.pressure}"
