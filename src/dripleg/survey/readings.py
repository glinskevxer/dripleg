"""What the instruments say, before anybody decides what it means.

Three readings come off a trap station and each one is close to useless alone.

Ultrasound says how much noise the seat is making and, if the technician held
the probe long enough, how often it cycled. Contact temperature says how hot
the pipe is either side of the trap. A sight glass says what the discharge
looks like, on the traps that have one.

None of these is a verdict, and this module very deliberately does not produce
one. It holds the numbers, derives the things that are pure arithmetic on the
numbers, and refuses readings that cannot have come off a real instrument.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from dripleg.errors import ValidationError
from dripleg.steam.saturated import at_pressure
from dripleg.units.pressure import Pressure
from dripleg.units.temperature import Temperature, TemperatureDelta

__all__ = [
    "SightGlassView",
    "SurveyMethod",
    "TemperatureReading",
    "UltrasonicReading",
]

MAX_DECIBELS = 120.0
MIN_PROBE_SECONDS = 5.0


class SurveyMethod(Enum):
    ULTRASONIC = "ultrasonic"
    CONTACT_TEMPERATURE = "contact_temperature"
    INFRARED = "infrared"
    SIGHT_GLASS = "sight_glass"
    VISUAL = "visual"
    ACOUSTIC_STETHOSCOPE = "stethoscope"

    @property
    def measures_sound(self) -> bool:
        return self in {SurveyMethod.ULTRASONIC, SurveyMethod.ACOUSTIC_STETHOSCOPE}

    @property
    def measures_temperature(self) -> bool:
        return self in {SurveyMethod.CONTACT_TEMPERATURE, SurveyMethod.INFRARED}

    @property
    def is_quantitative(self) -> bool:
        """Whether the method produces a number a rule can be written against."""

        return self is not SurveyMethod.VISUAL


class SightGlassView(Enum):
    """What can be seen through the glass, where there is one."""

    CONDENSATE = "condensate"
    FLASH = "flash"
    LIVE_STEAM = "live_steam"
    EMPTY = "empty"
    CANNOT_SEE = "cannot_see"

    @property
    def suggests_blow_through(self) -> bool:
        return self is SightGlassView.LIVE_STEAM

    @property
    def is_readable(self) -> bool:
        return self is not SightGlassView.CANNOT_SEE


@dataclass(frozen=True)
class UltrasonicReading:
    """One probe on the trap body, held for a while.

    `cycles` is how many discharges were counted in `seconds`. A technician who
    only took a level and did not count leaves it None, and every rule that
    wants a cycle rate has to cope with that rather than assume zero, because
    zero cycles is itself a finding.
    """

    decibels: float
    seconds: float
    cycles: int | None = None
    frequency_khz: float = 40.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.decibels <= MAX_DECIBELS:
            raise ValidationError(
                f"{self.decibels:g} dB is not a reading off this meter",
                field="decibels",
            )
        if self.seconds < MIN_PROBE_SECONDS:
            raise ValidationError(
                f"a probe held for {self.seconds:g} s is too short to count a cycle from",
                field="seconds",
            )
        if self.cycles is not None and self.cycles < 0:
            raise ValidationError("a cycle count is not negative", field="cycles")
        if self.frequency_khz <= 0:
            raise ValidationError("an ultrasonic probe has a frequency", field="frequency_khz")

    @property
    def counted_cycles(self) -> bool:
        return self.cycles is not None

    @property
    def cycles_per_minute(self) -> float | None:
        if self.cycles is None:
            return None
        return self.cycles * 60.0 / self.seconds

    @property
    def is_silent(self) -> bool:
        return self.decibels <= 5.0

    @property
    def sounded_continuous(self) -> bool:
        """Noise with no discharges counted in the window: a steady flow."""

        return self.cycles == 0 and not self.is_silent

    def louder_than(self, other: UltrasonicReading) -> bool:
        return self.decibels > other.decibels

    def __str__(self) -> str:
        if self.cycles_per_minute is None:
            return f"{self.decibels:.0f} dB"
        return f"{self.decibels:.0f} dB at {self.cycles_per_minute:.1f}/min"


@dataclass(frozen=True)
class TemperatureReading:
    """Pipe surface either side of the trap, and the air around it.

    Surface readings run below the steam inside. The correction is not applied
    here, because it depends on insulation and on the instrument, and burying
    it in the reading means nobody can see it later.
    """

    upstream: Temperature
    downstream: Temperature
    ambient: Temperature | None = None
    method: SurveyMethod = SurveyMethod.CONTACT_TEMPERATURE

    def __post_init__(self) -> None:
        if not self.method.measures_temperature:
            raise ValidationError(
                f"{self.method.value} does not measure a temperature",
                field="method",
            )
        if self.ambient is not None and self.ambient > self.upstream:
            raise ValidationError(
                "the air cannot be hotter than the pipe feeding the trap",
                field="ambient",
            )

    @property
    def differential(self) -> TemperatureDelta:
        """Upstream minus downstream. Positive is the normal direction."""

        gap = self.upstream - self.downstream
        assert isinstance(gap, TemperatureDelta)
        return gap

    @property
    def downstream_is_hot(self) -> bool:
        """Little or no drop across the trap, which is what steam past looks like."""

        return self.differential.fahrenheit < 20.0

    def subcooling_below(self, pressure: Pressure) -> TemperatureDelta:
        """How far under saturation the inlet pipe is running."""

        saturation = at_pressure(pressure).temperature
        gap = saturation - self.upstream
        assert isinstance(gap, TemperatureDelta)
        return gap

    def rise_above_ambient(self) -> TemperatureDelta | None:
        if self.ambient is None:
            return None
        gap = self.downstream - self.ambient
        assert isinstance(gap, TemperatureDelta)
        return gap

    def is_cold(self, pressure: Pressure) -> bool:
        """Both sides well under saturation, which is a trap that is not passing."""

        return self.subcooling_below(pressure).fahrenheit > 100.0

    def __str__(self) -> str:
        return f"{self.upstream} / {self.downstream}"
