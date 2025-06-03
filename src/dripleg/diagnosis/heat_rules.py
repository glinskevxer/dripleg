"""What the pipe temperatures say, and the one thing they cannot say.

Temperature is the method everybody trusts and it has a hole in it that no
amount of care closes: a trap discharging saturated condensate into a lower
pressure line produces flash steam, and flash steam is at exactly the same
temperature as the live steam a failed trap would be passing. The downstream
pipe reads the same either way.

So the temperature rules here do not claim to see blow through. They see steam
downstream, they say so, and they say it at a weight that needs the probe to
agree before it becomes a verdict. Rules that treat a hot outlet as proof are
the reason temperature only surveys condemn good traps.

What temperature is genuinely good at is the other failure: a cold trap. A
trap that is holding condensate back shows a cold inlet, and nothing else does.
"""

from __future__ import annotations

from dripleg.diagnosis.context import DiagnosisContext
from dripleg.diagnosis.evidence import Evidence
from dripleg.diagnosis.rules import Rule
from dripleg.steam.saturated import at_pressure
from dripleg.survey.condition import TrapCondition
from dripleg.survey.readings import SurveyMethod
from dripleg.units.temperature import Temperature

__all__ = [
    "HEAT_RULES",
    "ColdInlet",
    "ExcessSubcooling",
    "HealthyDrop",
    "HotOutlet",
    "WholeTrapCold",
    "expected_outlet",
]

# A surface reading runs under the steam inside the pipe. Anything within this
# of the discharge line's saturation temperature is steam as far as a contact
# probe can tell.
_OUTLET_MARGIN_F = 12.0

# Below saturation by this much and the trap is not passing anything.
_COLD_INLET_F = 100.0

# Within this of the air and the line is not live at all.
_AMBIENT_MARGIN_F = 35.0


def expected_outlet(context: DiagnosisContext) -> Temperature:
    """Saturation temperature in the line the trap discharges into."""

    return at_pressure(context.discharge_pressure).temperature


class _HeatRule(Rule):
    method = SurveyMethod.CONTACT_TEMPERATURE

    def applies_to(self, context: DiagnosisContext) -> bool:
        return context.has_heat


class HotOutlet(_HeatRule):
    code = "TMP-1"
    description = "outlet at discharge line saturation, which is steam of some kind"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        heat = context.heat
        assert heat is not None
        outlet_saturation = expected_outlet(context)
        if heat.downstream.fahrenheit < outlet_saturation.fahrenheit - _OUTLET_MARGIN_F:
            return []
        subcooling = context.subcooling
        if subcooling is not None and subcooling.fahrenheit > _COLD_INLET_F:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"outlet at {heat.downstream} against {outlet_saturation} saturation "
                    "in the discharge line, which flash and live steam share"
                ),
                supports=TrapCondition.BLOWING_THROUGH,
                weight=0.35,
                method=heat.method,
            )
        ]


class ColdInlet(_HeatRule):
    code = "TMP-2"
    description = "inlet a long way under saturation, so nothing is getting through"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        heat = context.heat
        subcooling = context.subcooling
        assert heat is not None
        assert subcooling is not None
        if subcooling.fahrenheit <= _COLD_INLET_F:
            return []
        # A thermostatic trap is supposed to back condensate up, so a cold
        # inlet on one of those is weaker evidence than on a disc.
        weight = 0.45 if context.principle.holds_condensate_back else 0.65
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"inlet {subcooling.fahrenheit:.0f} F under saturation at {context.pressure}"
                ),
                supports=TrapCondition.FAILED_CLOSED,
                weight=weight,
                method=heat.method,
            )
        ]


class WholeTrapCold(_HeatRule):
    code = "TMP-3"
    description = "both sides near the air temperature, so the line is not live"

    def applies_to(self, context: DiagnosisContext) -> bool:
        return context.has_heat and context.heat is not None and context.heat.ambient is not None

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        heat = context.heat
        assert heat is not None
        assert heat.ambient is not None
        rise = heat.upstream.fahrenheit - heat.ambient.fahrenheit
        if rise > _AMBIENT_MARGIN_F:
            return []
        return [
            Evidence(
                rule=self.code,
                statement=f"inlet only {rise:.0f} F above the air at {heat.ambient}",
                supports=TrapCondition.OUT_OF_SERVICE,
                weight=0.7,
                method=heat.method,
            )
        ]


class ExcessSubcooling(_HeatRule):
    code = "TMP-4"
    description = "inlet cooler than this principle works at, short of a cold trap"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        heat = context.heat
        subcooling = context.subcooling
        assert heat is not None
        assert subcooling is not None
        degrees = subcooling.fahrenheit
        if degrees > _COLD_INLET_F or degrees <= 0:
            return []
        if context.principle.subcooling_is_normal(degrees):
            return []
        _, band_top = context.principle.subcooling_f
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"inlet {degrees:.0f} F under saturation against a band topping out "
                    f"at {band_top:.0f} F"
                ),
                supports=TrapCondition.PLUGGED,
                weight=0.35,
                method=heat.method,
            )
        ]


class HealthyDrop(_HeatRule):
    code = "TMP-5"
    description = "hot inlet, cool outlet, which is a trap doing its job"

    def look(self, context: DiagnosisContext) -> list[Evidence]:
        heat = context.heat
        subcooling = context.subcooling
        assert heat is not None
        assert subcooling is not None
        outlet_saturation = expected_outlet(context)
        outlet_is_cool = (
            heat.downstream.fahrenheit < outlet_saturation.fahrenheit - _OUTLET_MARGIN_F
        )
        inlet_is_hot = context.principle.subcooling_is_normal(max(subcooling.fahrenheit, 0.0))
        if not (outlet_is_cool and inlet_is_hot):
            return []
        return [
            Evidence(
                rule=self.code,
                statement=(
                    f"{heat.differential.fahrenheit:.0f} F across the trap with the inlet in band"
                ),
                supports=TrapCondition.OK,
                weight=0.5,
                method=heat.method,
            )
        ]


HEAT_RULES: tuple[Rule, ...] = (
    HotOutlet(),
    ColdInlet(),
    WholeTrapCold(),
    ExcessSubcooling(),
    HealthyDrop(),
)
