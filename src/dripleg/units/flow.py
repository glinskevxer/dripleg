"""Mass, and mass per hour, which is how steam is bought, lost and argued about.

Everything in this package that says how much steam went somewhere says it in
pounds per hour, because that is the unit Napier's formula falls out in and the
unit a boiler nameplate carries. The metric readings convert on the way in and
on the way out, never in the middle.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

from dripleg.errors import UnitError, ValidationError

__all__ = ["Mass", "MassFlow", "MassFlowUnit", "MassUnit"]

_LB_PER_KG = 2.2046226218487757
_LB_PER_TONNE = 1000.0 * _LB_PER_KG
_LB_PER_SHORT_TON = 2000.0

HOURS_PER_YEAR = 8760.0


class MassUnit(Enum):
    POUND = "lb"
    KILOGRAM = "kg"
    TONNE = "t"
    SHORT_TON = "ton"


class MassFlowUnit(Enum):
    POUND_PER_HOUR = "lb/h"
    KILOGRAM_PER_HOUR = "kg/h"
    TONNE_PER_HOUR = "t/h"


_MASS_SPELLINGS = {
    "lb": MassUnit.POUND,
    "lbs": MassUnit.POUND,
    "pound": MassUnit.POUND,
    "pounds": MassUnit.POUND,
    "kg": MassUnit.KILOGRAM,
    "kilogram": MassUnit.KILOGRAM,
    "kilograms": MassUnit.KILOGRAM,
    "t": MassUnit.TONNE,
    "tonne": MassUnit.TONNE,
    "tonnes": MassUnit.TONNE,
    "mt": MassUnit.TONNE,
    "ton": MassUnit.SHORT_TON,
    "tons": MassUnit.SHORT_TON,
}

_FLOW_SPELLINGS = {
    "lb/h": MassFlowUnit.POUND_PER_HOUR,
    "lb/hr": MassFlowUnit.POUND_PER_HOUR,
    "lbh": MassFlowUnit.POUND_PER_HOUR,
    "pph": MassFlowUnit.POUND_PER_HOUR,
    "lb per hour": MassFlowUnit.POUND_PER_HOUR,
    "kg/h": MassFlowUnit.KILOGRAM_PER_HOUR,
    "kg/hr": MassFlowUnit.KILOGRAM_PER_HOUR,
    "kgh": MassFlowUnit.KILOGRAM_PER_HOUR,
    "t/h": MassFlowUnit.TONNE_PER_HOUR,
    "t/hr": MassFlowUnit.TONNE_PER_HOUR,
    "tph": MassFlowUnit.TONNE_PER_HOUR,
}

_TEXT = re.compile(r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+)\s*(?P<unit>[a-zA-Z/ ]*)\s*$")


def _clean(unit: str) -> str:
    return " ".join(unit.lower().replace("_", " ").split())


@dataclass(frozen=True, order=True)
class Mass:
    """A quantity of steam or condensate, held in pounds."""

    pounds: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.pounds):
            raise ValidationError("mass is not a finite number", field="mass")
        if self.pounds < 0:
            raise ValidationError(f"mass cannot be negative, got {self.pounds:g} lb", field="mass")

    @classmethod
    def from_pounds(cls, value: float) -> Mass:
        return cls(value)

    @classmethod
    def from_kilograms(cls, value: float) -> Mass:
        return cls(value * _LB_PER_KG)

    @classmethod
    def from_tonnes(cls, value: float) -> Mass:
        return cls(value * _LB_PER_TONNE)

    @classmethod
    def from_short_tons(cls, value: float) -> Mass:
        return cls(value * _LB_PER_SHORT_TON)

    @classmethod
    def of(cls, value: float, unit: MassUnit | str) -> Mass:
        resolved = unit if isinstance(unit, MassUnit) else _MASS_SPELLINGS.get(_clean(unit))
        if resolved is None:
            raise UnitError(f"unknown mass unit {unit!r}", field="mass")
        builders = {
            MassUnit.POUND: cls.from_pounds,
            MassUnit.KILOGRAM: cls.from_kilograms,
            MassUnit.TONNE: cls.from_tonnes,
            MassUnit.SHORT_TON: cls.from_short_tons,
        }
        return builders[resolved](value)

    @property
    def kilograms(self) -> float:
        return self.pounds / _LB_PER_KG

    @property
    def tonnes(self) -> float:
        return self.pounds / _LB_PER_TONNE

    @property
    def short_tons(self) -> float:
        return self.pounds / _LB_PER_SHORT_TON

    def __add__(self, other: Mass) -> Mass:
        return Mass(self.pounds + other.pounds)

    def __mul__(self, factor: float) -> Mass:
        return Mass(self.pounds * factor)

    def over(self, hours: float) -> MassFlow:
        """Spread this mass evenly across a run and call it a rate."""

        if hours <= 0:
            raise ValidationError("a run has to be longer than zero hours", field="hours")
        return MassFlow(self.pounds / hours)

    def __str__(self) -> str:
        if self.pounds >= 2_000_000:
            return f"{self.pounds / 1_000_000:.2f} Mlb"
        return f"{self.pounds:,.0f} lb"


@dataclass(frozen=True, order=True)
class MassFlow:
    """A rate, held in pounds per hour."""

    pounds_per_hour: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.pounds_per_hour):
            raise ValidationError("flow is not a finite number", field="flow")
        if self.pounds_per_hour < 0:
            raise ValidationError(
                f"flow cannot be negative, got {self.pounds_per_hour:g} lb/h",
                field="flow",
            )

    @classmethod
    def zero(cls) -> MassFlow:
        return cls(0.0)

    @classmethod
    def from_pounds_per_hour(cls, value: float) -> MassFlow:
        return cls(value)

    @classmethod
    def from_kilograms_per_hour(cls, value: float) -> MassFlow:
        return cls(value * _LB_PER_KG)

    @classmethod
    def from_tonnes_per_hour(cls, value: float) -> MassFlow:
        return cls(value * _LB_PER_TONNE)

    @classmethod
    def of(cls, value: float, unit: MassFlowUnit | str) -> MassFlow:
        resolved = unit if isinstance(unit, MassFlowUnit) else _FLOW_SPELLINGS.get(_clean(unit))
        if resolved is None:
            raise UnitError(f"unknown flow unit {unit!r}", field="flow")
        builders = {
            MassFlowUnit.POUND_PER_HOUR: cls.from_pounds_per_hour,
            MassFlowUnit.KILOGRAM_PER_HOUR: cls.from_kilograms_per_hour,
            MassFlowUnit.TONNE_PER_HOUR: cls.from_tonnes_per_hour,
        }
        return builders[resolved](value)

    @classmethod
    def parse(cls, text: str) -> MassFlow:
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as a flow", field="flow")
        unit_text = match.group("unit").strip()
        if not unit_text:
            raise UnitError(f"{text!r} has no unit on it", field="flow")
        return cls.of(float(match.group("value")), unit_text)

    @property
    def kilograms_per_hour(self) -> float:
        return self.pounds_per_hour / _LB_PER_KG

    @property
    def tonnes_per_hour(self) -> float:
        return self.pounds_per_hour / _LB_PER_TONNE

    @property
    def is_zero(self) -> bool:
        return self.pounds_per_hour == 0.0

    def over(self, hours: float) -> Mass:
        """What this rate carries in the hours the leg is actually live."""

        if hours < 0:
            raise ValidationError("hours cannot be negative", field="hours")
        return Mass(self.pounds_per_hour * hours)

    def annual(self, hours: float = HOURS_PER_YEAR) -> Mass:
        return self.over(hours)

    def scaled(self, factor: float) -> MassFlow:
        if factor < 0:
            raise ValidationError("a flow factor cannot be negative", field="factor")
        return MassFlow(self.pounds_per_hour * factor)

    def __add__(self, other: MassFlow) -> MassFlow:
        return MassFlow(self.pounds_per_hour + other.pounds_per_hour)

    def __str__(self) -> str:
        return f"{self.pounds_per_hour:,.1f} lb/h"
