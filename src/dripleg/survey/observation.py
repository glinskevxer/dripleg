"""One line of a survey: a trap, a day, a technician and what was measured.

The reported condition is what the person in the plant room wrote down. It is
kept exactly as given and it is never overwritten, because the diagnosis engine
later produces its own verdict and the interesting reports are the ones where
the two disagree. A technician who calls everything a pass and a rule set that
calls a third of the route blowing through is a training problem, and it is
only visible if both numbers survive.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from dripleg.errors import ValidationError
from dripleg.model.tags import TrapTag
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import (
    SightGlassView,
    SurveyMethod,
    TemperatureReading,
    UltrasonicReading,
)
from dripleg.units.pressure import Pressure

__all__ = ["Observation"]

MAX_NOTE = 400


@dataclass(frozen=True)
class Observation:
    """What one trap looked like on one day."""

    tag: TrapTag
    observed_on: dt.date
    technician: str
    reported_condition: TrapCondition
    ultrasonic: UltrasonicReading | None = None
    temperature: TemperatureReading | None = None
    sight_glass: SightGlassView | None = None
    measured_pressure: Pressure | None = None
    note: str = ""
    photo_reference: str | None = None

    def __post_init__(self) -> None:
        who = " ".join(self.technician.split())
        if not who:
            raise ValidationError("an observation has to say who took it", field="technician")
        object.__setattr__(self, "technician", who)
        cleaned = " ".join(self.note.split())
        if len(cleaned) > MAX_NOTE:
            raise ValidationError(f"a note stops at {MAX_NOTE} characters", field="note")
        object.__setattr__(self, "note", cleaned)
        if not self.reported_condition.was_assessed and self.has_measurements:
            raise ValidationError(
                "a trap that was not reached cannot carry readings",
                field="reported_condition",
            )
        if self.photo_reference is not None and not self.photo_reference.strip():
            raise ValidationError("a photo reference cannot be blank", field="photo_reference")

    @property
    def has_measurements(self) -> bool:
        return any(
            (
                self.ultrasonic is not None,
                self.temperature is not None,
                self.sight_glass is not None,
            )
        )

    @property
    def methods_used(self) -> list[SurveyMethod]:
        used: list[SurveyMethod] = []
        if self.ultrasonic is not None:
            used.append(SurveyMethod.ULTRASONIC)
        if self.temperature is not None:
            used.append(self.temperature.method)
        if self.sight_glass is not None and self.sight_glass.is_readable:
            used.append(SurveyMethod.SIGHT_GLASS)
        if not used:
            used.append(SurveyMethod.VISUAL)
        return used

    @property
    def is_two_method(self) -> bool:
        """Whether sound and temperature were both taken.

        The survey standard here calls a single method reading provisional. It
        is not thrown away, but a repair recommendation off one method alone
        gets flagged rather than issued.
        """

        return self.ultrasonic is not None and self.temperature is not None

    @property
    def cycles_per_minute(self) -> float | None:
        return None if self.ultrasonic is None else self.ultrasonic.cycles_per_minute

    def pressure_or(self, fallback: Pressure) -> Pressure:
        """The measured header pressure, or the one on the register."""

        return self.measured_pressure if self.measured_pressure is not None else fallback

    def with_note(self, note: str) -> Observation:
        return Observation(**{**self.__dict__, "note": note})

    @property
    def key(self) -> tuple[str, dt.date]:
        return (str(self.tag), self.observed_on)

    def __str__(self) -> str:
        return f"{self.tag} {self.observed_on} {self.reported_condition.label}"
