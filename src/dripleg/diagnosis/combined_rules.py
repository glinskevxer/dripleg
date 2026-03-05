"""The sight glass, and the two readings held up against each other.

A sight glass settles the question the other two methods cannot: whether what
is going down the line is flash or live steam. Very few traps have one, which
is why the rest of this package works so hard without it, but where there is
one it outranks everything.

The corroboration rules at the bottom are not meta rules. They do not look at
what other rules concluded, they look at the readings again and ask a question
neither method can ask alone. Loud and cold at the same time is the clearest
example: sound alone calls it a leak, temperature alone calls it a cold trap,
and the pair of them together is a blocked strainer with steam whistling past
the blockage.
"""

from __future__ import annotations

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.evidence import Evidence
from dripleg.diagnosis.heat_rules import expected_outlet
from dripleg.diagnosis.rules import Rule
from dripleg.diagnosis.sound_rules import sound_bands
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SightGlassView, SurveyMethod
from dripleg.thresholds import COLD_INLET_F, OUTLET_MARGIN_F

__all__ = [
    "COMBINED_RULES",
    "GlassCondensate",
    "GlassEmpty",
    "GlassFlash",
    "GlassLiveSteam",
    "LoudAndCold",
    "QuietAndCold",
    "SoundAndHeatAgree",
]


class _GlassRule(Rule):
    method = SurveyMethod.SIGHT_GLASS

    def applies_to(self, context: DiagnosisContext) -> bool:
        glass = context.observation.sight_glass
        return glass is not None and glass.is_readable


class GlassLiveSteam(_GlassRule):
    code = "VIS-1"
    description = "live steam through the glass, which nothing else can prove"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        if context.observation.sight_glass is not SightGlassView.LIVE_STEAM:
            return []
        return [
            Evidence(
                rule=self.code,
                statement="live steam seen through the sight glass",
                supports=TrapCondition.BLOWING_THROUGH,
                weight=1.0,
                method=self.method,
            )
        ]


class GlassCondensate(_GlassRule):
    code = "VIS-2"
    description = "condensate through the glass, which is the trap working"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        if context.observation.sight_glass is not SightGlassView.CONDENSATE:
            return []
        return [
            Evidence(
                rule=self.code,
                statement="condensate running through the sight glass",
                supports=TrapCondition.OK,
                weight=0.7,
                method=self.method,
            )
        ]


class GlassFlash(_GlassRule):
    code = "VIS-3"
    description = "flash through the glass, which is normal and is not a leak"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        if context.observation.sight_glass is not SightGlassView.FLASH:
            return []
        return [
            Evidence(
                rule=self.code,
                statement="flash off the discharge, not live steam",
                supports=TrapCondition.OK,
                weight=0.4,
                method=self.method,
            )
        ]


class GlassEmpty(_GlassRule):
    code = "VIS-4"
    description = "nothing moving through the glass at all"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        if context.observation.sight_glass is not SightGlassView.EMPTY:
            return []
        return [
            Evidence(
                rule=self.code,
                statement="nothing moving through the sight glass",
                supports=TrapCondition.FAILED_CLOSED,
                weight=0.35,
                method=self.method,
            )
        ]


class _PairRule(Rule):
    method = SurveyMethod.ULTRASONIC

    def applies_to(self, context: DiagnosisContext) -> bool:
        return context.has_sound and context.has_heat


class SoundAndHeatAgree(_PairRule):
    code = "COR-1"
    description = "loud seat and an outlet at saturation, which flash alone will not do"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        heat = context.heat
        assert sound is not None
        assert heat is not None
        _, _, blow = sound_bands(context)
        outlet_saturation = expected_outlet(context)
        outlet_hot = heat.downstream.fahrenheit >= outlet_saturation.fahrenheit - OUTLET_MARGIN_F
        if sound.decibels < blow or not outlet_hot:
            return []
        if sound.counted_cycles and not sound.sounded_continuous:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"{sound.decibels:.0f} dB with no cycling and an outlet at "
                    f"{heat.downstream}, both methods agreeing"
                ),
                supports=TrapCondition.BLOWING_THROUGH,
                weight=0.8,
                method=self.method,
            )
        ]


class LoudAndCold(_PairRule):
    code = "COR-2"
    description = "noise at the seat with a cold inlet, which is a blockage being forced"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        subcooling = context.subcooling
        assert sound is not None
        assert subcooling is not None
        _, leak, _ = sound_bands(context)
        if sound.decibels < leak:
            return []
        if subcooling.fahrenheit <= COLD_INLET_F:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"{sound.decibels:.0f} dB at the seat with the inlet "
                    f"{subcooling.fahrenheit:.0f} F under saturation"
                ),
                supports=TrapCondition.PLUGGED,
                weight=0.6,
                method=self.method,
            )
        ]


class QuietAndCold(_PairRule):
    code = "COR-3"
    description = "silent and cold together, which is a trap doing nothing at all"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        sound = context.sound
        subcooling = context.subcooling
        assert sound is not None
        assert subcooling is not None
        quiet, _, _ = sound_bands(context)
        if sound.decibels > quiet or subcooling.fahrenheit <= COLD_INLET_F:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"{sound.decibels:.0f} dB and the inlet "
                    f"{subcooling.fahrenheit:.0f} F under saturation"
                ),
                supports=TrapCondition.FAILED_CLOSED,
                weight=0.85,
                method=self.method,
            )
        ]


COMBINED_RULES: tuple[Rule, ...] = (
    GlassLiveSteam(),
    GlassCondensate(),
    GlassFlash(),
    GlassEmpty(),
    SoundAndHeatAgree(),
    LoudAndCold(),
    QuietAndCold(),
)
