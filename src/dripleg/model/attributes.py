"""What a trap drains, how hard it is to reach, and what breaks if it fails.

These three end up multiplied together in the repair priority, so they are
written as enums with the weights attached rather than as free text with a
lookup somewhere else. The weights are the survey standard's, and the point of
keeping them here is that changing one changes every report at once and shows
up as one line in a diff.

Access is the one people get wrong. A leaking trap up a ladder inside a live
process building does not cost the same to change as one at head height by the
door, and a priority list that ignores that sends the crew to the wrong jobs
all week.
"""

from __future__ import annotations

from enum import Enum

from dripleg.errors import ValidationError

__all__ = ["Accessibility", "Criticality", "ServiceType"]


class ServiceType(Enum):
    """What the trap is draining."""

    DRIP = "drip"
    TRACER = "tracer"
    PROCESS_COIL = "process_coil"
    UNIT_HEATER = "unit_heater"
    SHELL_AND_TUBE = "shell_and_tube"
    JACKETED_VESSEL = "jacketed_vessel"
    SEPARATOR = "separator"
    TURBINE_DRAIN = "turbine_drain"
    STERILISER = "steriliser"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ")

    @property
    def is_process(self) -> bool:
        """Process service carries load. Drip and tracer service mostly does not."""

        return self in {
            ServiceType.PROCESS_COIL,
            ServiceType.SHELL_AND_TUBE,
            ServiceType.JACKETED_VESSEL,
            ServiceType.STERILISER,
        }

    @property
    def condensate_load_varies(self) -> bool:
        """Whether the load swings, which is what a float trap is for."""

        return self.is_process or self is ServiceType.UNIT_HEATER

    @property
    def failure_stops_production(self) -> bool:
        """A trap failed closed on this service backs condensate into the work."""

        return self in {
            ServiceType.PROCESS_COIL,
            ServiceType.SHELL_AND_TUBE,
            ServiceType.JACKETED_VESSEL,
            ServiceType.STERILISER,
            ServiceType.TURBINE_DRAIN,
        }

    @property
    def survey_interval_months(self) -> int:
        """How often this service is looked at when nothing else says otherwise."""

        return {
            ServiceType.TURBINE_DRAIN: 6,
            ServiceType.PROCESS_COIL: 6,
            ServiceType.STERILISER: 6,
            ServiceType.SHELL_AND_TUBE: 12,
            ServiceType.JACKETED_VESSEL: 12,
            ServiceType.SEPARATOR: 12,
            ServiceType.UNIT_HEATER: 12,
            ServiceType.DRIP: 12,
            ServiceType.TRACER: 24,
        }[self]


class Accessibility(Enum):
    """How much work it is to get a hand on the trap."""

    GROUND_LEVEL = "ground_level"
    LADDER = "ladder"
    PLATFORM = "platform"
    SCAFFOLD_REQUIRED = "scaffold_required"
    CONFINED_SPACE = "confined_space"
    HOT_WORK_PERMIT = "hot_work_permit"
    SHUTDOWN_ONLY = "shutdown_only"

    @property
    def labour_multiplier(self) -> float:
        """Against a ground level change out of one hour."""

        return {
            Accessibility.GROUND_LEVEL: 1.0,
            Accessibility.LADDER: 1.4,
            Accessibility.PLATFORM: 1.2,
            Accessibility.SCAFFOLD_REQUIRED: 4.0,
            Accessibility.CONFINED_SPACE: 5.0,
            Accessibility.HOT_WORK_PERMIT: 2.5,
            Accessibility.SHUTDOWN_ONLY: 8.0,
        }[self]

    @property
    def needs_a_permit(self) -> bool:
        return self in {
            Accessibility.CONFINED_SPACE,
            Accessibility.HOT_WORK_PERMIT,
        }

    @property
    def can_be_done_running(self) -> bool:
        return self is not Accessibility.SHUTDOWN_ONLY

    @property
    def surveyable_on_a_normal_route(self) -> bool:
        """Whether a technician can read it without arranging anything."""

        return self in {
            Accessibility.GROUND_LEVEL,
            Accessibility.LADDER,
            Accessibility.PLATFORM,
        }


class Criticality(Enum):
    """What it costs the plant if this trap is wrong."""

    SAFETY = "safety"
    PRODUCTION = "production"
    QUALITY = "quality"
    COMFORT = "comfort"
    NUISANCE = "nuisance"

    @property
    def weight(self) -> float:
        return {
            Criticality.SAFETY: 5.0,
            Criticality.PRODUCTION: 3.0,
            Criticality.QUALITY: 2.0,
            Criticality.COMFORT: 1.2,
            Criticality.NUISANCE: 1.0,
        }[self]

    @property
    def escalates_immediately(self) -> bool:
        return self is Criticality.SAFETY

    @classmethod
    def parse(cls, text: str) -> Criticality:
        key = text.strip().lower().replace(" ", "_")
        for member in cls:
            if member.value == key:
                return member
        raise ValidationError(f"{text!r} is not a criticality", field="criticality")
