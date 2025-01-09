"""Temperature, and the difference between two of them, which is not the same
type at all.

A technician shoots the pipe above a trap and the pipe below it and writes down
both numbers plus the gap. The gap is where the type discipline earns its keep:
a 40 degree drop is 40 delta F or 22.2 delta C, and converting it the way you
convert a reading gives 4.4, which is wrong and looks plausible. So a reading
and a difference are separate types and the only way between them is
subtraction.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

from dripleg.errors import UnitError, ValidationError

__all__ = [
    "ABSOLUTE_ZERO_F",
    "Temperature",
    "TemperatureDelta",
    "TemperatureUnit",
]

ABSOLUTE_ZERO_F = -459.67

_F_PER_C = 1.8


class TemperatureUnit(Enum):
    FAHRENHEIT = "F"
    CELSIUS = "C"
    KELVIN = "K"
    RANKINE = "R"


_SPELLINGS = {
    "f": TemperatureUnit.FAHRENHEIT,
    "degf": TemperatureUnit.FAHRENHEIT,
    "deg f": TemperatureUnit.FAHRENHEIT,
    "fahrenheit": TemperatureUnit.FAHRENHEIT,
    "c": TemperatureUnit.CELSIUS,
    "degc": TemperatureUnit.CELSIUS,
    "deg c": TemperatureUnit.CELSIUS,
    "celsius": TemperatureUnit.CELSIUS,
    "k": TemperatureUnit.KELVIN,
    "kelvin": TemperatureUnit.KELVIN,
    "r": TemperatureUnit.RANKINE,
    "rankine": TemperatureUnit.RANKINE,
}

_TEXT = re.compile(r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+)\s*°?\s*(?P<unit>[a-zA-Z ]*)\s*$")


def _resolve(unit: TemperatureUnit | str) -> TemperatureUnit:
    if isinstance(unit, TemperatureUnit):
        return unit
    key = " ".join(unit.lower().replace("_", " ").replace("°", "").split())
    try:
        return _SPELLINGS[key]
    except KeyError:
        raise UnitError(f"unknown temperature unit {unit!r}", field="temperature") from None


@dataclass(frozen=True, order=True)
class Temperature:
    """A reading on the thermometer, held in Fahrenheit."""

    fahrenheit: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.fahrenheit):
            raise ValidationError("temperature is not a finite number", field="temperature")
        if self.fahrenheit < ABSOLUTE_ZERO_F:
            raise ValidationError(
                f"{self.fahrenheit:g} F is below absolute zero",
                field="temperature",
            )

    @classmethod
    def from_fahrenheit(cls, value: float) -> Temperature:
        return cls(value)

    @classmethod
    def from_celsius(cls, value: float) -> Temperature:
        return cls(value * _F_PER_C + 32.0)

    @classmethod
    def from_kelvin(cls, value: float) -> Temperature:
        return cls(value * _F_PER_C + ABSOLUTE_ZERO_F)

    @classmethod
    def from_rankine(cls, value: float) -> Temperature:
        return cls(value + ABSOLUTE_ZERO_F)

    @classmethod
    def of(cls, value: float, unit: TemperatureUnit | str) -> Temperature:
        builders = {
            TemperatureUnit.FAHRENHEIT: cls.from_fahrenheit,
            TemperatureUnit.CELSIUS: cls.from_celsius,
            TemperatureUnit.KELVIN: cls.from_kelvin,
            TemperatureUnit.RANKINE: cls.from_rankine,
        }
        return builders[_resolve(unit)](value)

    @classmethod
    def parse(cls, text: str) -> Temperature:
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as a temperature", field="temperature")
        unit_text = match.group("unit").strip()
        if not unit_text:
            raise UnitError(f"{text!r} has no unit on it", field="temperature")
        return cls.of(float(match.group("value")), unit_text)

    @property
    def celsius(self) -> float:
        return (self.fahrenheit - 32.0) / _F_PER_C

    @property
    def kelvin(self) -> float:
        return (self.fahrenheit - ABSOLUTE_ZERO_F) / _F_PER_C

    @property
    def rankine(self) -> float:
        return self.fahrenheit - ABSOLUTE_ZERO_F

    def __sub__(self, other: Temperature | TemperatureDelta) -> Temperature | TemperatureDelta:
        if isinstance(other, Temperature):
            return TemperatureDelta(self.fahrenheit - other.fahrenheit)
        return Temperature(self.fahrenheit - other.fahrenheit)

    def __add__(self, other: TemperatureDelta) -> Temperature:
        if not isinstance(other, TemperatureDelta):
            raise TypeError("only a temperature difference can be added to a temperature")
        return Temperature(self.fahrenheit + other.fahrenheit)

    def __str__(self) -> str:
        return f"{self.fahrenheit:.1f} F"

    def __repr__(self) -> str:
        return f"Temperature(fahrenheit={self.fahrenheit:.6g})"


@dataclass(frozen=True, order=True)
class TemperatureDelta:
    """The gap between two readings, held in Fahrenheit degrees.

    Unlike a reading this may be negative, and it converts by scale only.
    """

    fahrenheit: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.fahrenheit):
            raise ValidationError("temperature difference is not finite", field="temperature")

    @classmethod
    def from_fahrenheit(cls, value: float) -> TemperatureDelta:
        return cls(value)

    @classmethod
    def from_celsius(cls, value: float) -> TemperatureDelta:
        return cls(value * _F_PER_C)

    @property
    def celsius(self) -> float:
        return self.fahrenheit / _F_PER_C

    @property
    def is_rise(self) -> bool:
        return self.fahrenheit > 0

    def __abs__(self) -> TemperatureDelta:
        return TemperatureDelta(abs(self.fahrenheit))

    def __neg__(self) -> TemperatureDelta:
        return TemperatureDelta(-self.fahrenheit)

    def __add__(self, other: TemperatureDelta) -> TemperatureDelta:
        return TemperatureDelta(self.fahrenheit + other.fahrenheit)

    def __str__(self) -> str:
        return f"{self.fahrenheit:+.1f} dF"
