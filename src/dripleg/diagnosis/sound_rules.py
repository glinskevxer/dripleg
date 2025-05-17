"""What the ultrasonic probe hears, read against pressure and principle.

Two things make a raw decibel number useless on its own.

The first is pressure. A healthy trap on a 250 psig header is louder than a
failed one on a 10 psig line, because the noise is flow noise and the flow goes
up with the pressure drop. So the thresholds are a table by pressure class, not
a constant.

The second is the principle. An inverted bucket that goes quiet between
discharges sounds nothing like a float trap, which never goes quiet at all. A
continuous rush is a failure on the first and normal operation on the second,
and reading the level without knowing which is in front of you gets it exactly
backwards on half the population.
"""

from __future__ import annotations

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.evidence import Evidence
from dripleg.diagnosis.rules import Rule
from dripleg.model.header import PressureClass
from dripleg.model.principles import DischargePattern
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SurveyMethod

__all__ = [
    "SOUND_RULES",
    "CycleRateHigh",
    "HealthyCycling",
    "LevelBlowThrough",
    "LevelLeaking",
    "NoCyclesOnCyclingTrap",
    "Silent",
    "sound_bands",
]

# silent ceiling, leaking floor, blow through floor, in dB on a 40 kHz probe.
_BANDS: dict[PressureClass, tuple[float, float, float]] = {
    PressureClass.VACUUM: (8.0, 24.0, 36.0),
    PressureClass.LOW: (10.0, 30.0, 45.0),
    PressureClass.MEDIUM: (14.0, 38.0, 55.0),
    PressureClass.HIGH: (18.0, 45.0, 62.0),
}


def sound_bands(context: DiagnosisContext) -> tuple[float, float, float]:
    """The three levels that matter, for the pressure this trap is at."""

    return _BANDS[PressureClass.of(context.pressure)]


class _SoundRule(Rule):
    method = SurveyMethod.ULTRASONIC

    def applies_to(self, context: DiagnosisContext) -> bool:
        return context.has_sound


class LevelBlowThrough(_SoundRule):
    code = "SND-1"
    description = "loud and not cycling, at this pressure, is live steam through the seat"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        assert sound is not None
        _, _, blow = sound_bands(context)
        if sound.decibels < blow:
            return []
        if sound.counted_cycles and not sound.sounded_continuous:
            return []
        # A trap whose healthy state is a continuous flow is quieter evidence,
        # because the noise it makes when it is working is the same noise.
        continuous_by_design = context.principle.pattern is DischargePattern.CONTINUOUS
        weight = 0.45 if continuous_by_design else 0.75
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"{sound.decibels:.0f} dB steady against a {blow:.0f} dB floor "
                    f"for a {context.pressure} header"
                ),
                supports=TrapCondition.BLOWING_THROUGH,
                weight=weight,
                method=self.method,
            )
        ]


class LevelLeaking(_SoundRule):
    code = "SND-2"
    description = "noise above the working band but short of blow through is a leaking seat"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        assert sound is not None
        _, leak, blow = sound_bands(context)
        if not leak <= sound.decibels < blow:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"{sound.decibels:.0f} dB, between the {leak:.0f} and {blow:.0f} dB marks"
                ),
                supports=TrapCondition.LEAKING,
                weight=0.45,
                method=self.method,
            )
        ]


class Silent(_SoundRule):
    code = "SND-3"
    description = "nothing at all through the probe on a trap that should be passing"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        assert sound is not None
        quiet, _, _ = sound_bands(context)
        if sound.decibels > quiet:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=f"{sound.decibels:.0f} dB, under the {quiet:.0f} dB working floor",
                supports=TrapCondition.FAILED_CLOSED,
                weight=0.4,
                method=self.method,
            )
        ]


class CycleRateHigh(_SoundRule):
    code = "SND-4"
    description = "discharging far more often than the principle should"

    def applies_to(self, context: DiagnosisContext) -> bool:
        return context.has_sound and context.cycles_per_minute is not None

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        rate = context.cycles_per_minute
        assert rate is not None
        low, high = context.principle.cycles_per_minute
        if rate <= high:
            return []
        severe = rate > high * 2
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"{rate:.1f} cycles a minute against a {low:.1f} to {high:.1f} band "
                    f"for {context.principle.principle.label}"
                ),
                supports=TrapCondition.RAPID_CYCLING,
                weight=0.7 if severe else 0.5,
                method=self.method,
            )
        ]


class NoCyclesOnCyclingTrap(_SoundRule):
    code = "SND-5"
    description = "an intermittent trap making noise without ever shutting"

    def applies_to(self, context: DiagnosisContext) -> bool:
        if not context.has_sound:
            return False
        sound = context.sound
        assert sound is not None
        return sound.counted_cycles and context.principle.pattern.is_audible_cycling

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        assert sound is not None
        if not sound.sounded_continuous:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"no discharges counted in {sound.seconds:.0f} s at "
                    f"{sound.decibels:.0f} dB on a {context.principle.pattern.value} trap"
                ),
                supports=TrapCondition.BLOWING_THROUGH,
                weight=0.6,
                method=self.method,
            )
        ]


class HealthyCycling(_SoundRule):
    code = "SND-6"
    description = "cycling inside its band and quieter than the blow through floor"

    def applies_to(self, context: DiagnosisContext) -> bool:
        return (
            context.has_sound
            and context.cycles_per_minute is not None
            and context.principle.pattern.is_audible_cycling
        )

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        rate = context.cycles_per_minute
        assert sound is not None
        assert rate is not None
        _, _, blow = sound_bands(context)
        if sound.decibels >= blow or not context.principle.cycle_rate_is_normal(rate):
            return []
        return [
            Evidence(
                rule=self.code,
                statement=f"{rate:.1f} cycles a minute at {sound.decibels:.0f} dB, both in band",
                supports=TrapCondition.OK,
                weight=0.55,
                method=self.method,
            )
        ]


SOUND_RULES: tuple[Rule, ...] = (
    LevelBlowThrough(),
    LevelLeaking(),
    Silent(),
    CycleRateHigh(),
    NoCyclesOnCyclingTrap(),
    HealthyCycling(),
)
