"""Energy and energy rate, held in British thermal units.

Fuel is bought by the MMBtu, steam enthalpy is published in Btu per pound, and
the two have to multiply cleanly or the loss report is off by a thousand. So
everything lands in Btu and the report layer picks the size it wants to print.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

from dripleg.errors import UnitError, ValidationError
from dripleg.units.flow import HOURS_PER_YEAR, Mass, MassFlow

__all__ = ["Energy", "EnergyRate", "EnergyUnit", "SpecificEnthalpy"]

_BTU_PER_MMBTU = 1_000_000.0
_BTU_PER_MJ = 947.8171203133172
_BTU_PER_KWH = 3412.141633127942
_BTU_PER_THERM = 100_000.0
_BTU_PER_HOUR_PER_KW = _BTU_PER_KWH
_BTU_PER_BOILER_HORSEPOWER_HOUR = 33475.0


class EnergyUnit(Enum):
    BTU = "btu"
    MMBTU = "mmbtu"
    MEGAJOULE = "mj"
    GIGAJOULE = "gj"
    KILOWATT_HOUR = "kwh"
    THERM = "therm"


_SPELLINGS = {
    "btu": EnergyUnit.BTU,
    "btus": EnergyUnit.BTU,
    "mmbtu": EnergyUnit.MMBTU,
    "mm btu": EnergyUnit.MMBTU,
    "dth": EnergyUnit.MMBTU,
    "dekatherm": EnergyUnit.MMBTU,
    "mj": EnergyUnit.MEGAJOULE,
    "megajoule": EnergyUnit.MEGAJOULE,
    "gj": EnergyUnit.GIGAJOULE,
    "gigajoule": EnergyUnit.GIGAJOULE,
    "kwh": EnergyUnit.KILOWATT_HOUR,
    "kw h": EnergyUnit.KILOWATT_HOUR,
    "therm": EnergyUnit.THERM,
    "therms": EnergyUnit.THERM,
}

_TEXT = re.compile(r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+)\s*(?P<unit>[a-zA-Z ]*)\s*$")


@dataclass(frozen=True, order=True)
class Energy:
    """A quantity of heat, held in Btu."""

    btu: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.btu):
            raise ValidationError("energy is not a finite number", field="energy")
        if self.btu < 0:
            raise ValidationError(
                f"energy cannot be negative, got {self.btu:g} Btu", field="energy"
            )

    @classmethod
    def zero(cls) -> Energy:
        return cls(0.0)

    @classmethod
    def from_btu(cls, value: float) -> Energy:
        return cls(value)

    @classmethod
    def from_mmbtu(cls, value: float) -> Energy:
        return cls(value * _BTU_PER_MMBTU)

    @classmethod
    def from_megajoules(cls, value: float) -> Energy:
        return cls(value * _BTU_PER_MJ)

    @classmethod
    def from_gigajoules(cls, value: float) -> Energy:
        return cls(value * _BTU_PER_MJ * 1000.0)

    @classmethod
    def from_kilowatt_hours(cls, value: float) -> Energy:
        return cls(value * _BTU_PER_KWH)

    @classmethod
    def from_therms(cls, value: float) -> Energy:
        return cls(value * _BTU_PER_THERM)

    @classmethod
    def of(cls, value: float, unit: EnergyUnit | str) -> Energy:
        resolved = unit
        if not isinstance(resolved, EnergyUnit):
            key = " ".join(str(unit).lower().replace("_", " ").replace("-", " ").split())
            found = _SPELLINGS.get(key)
            if found is None:
                raise UnitError(f"unknown energy unit {unit!r}", field="energy")
            resolved = found
        builders = {
            EnergyUnit.BTU: cls.from_btu,
            EnergyUnit.MMBTU: cls.from_mmbtu,
            EnergyUnit.MEGAJOULE: cls.from_megajoules,
            EnergyUnit.GIGAJOULE: cls.from_gigajoules,
            EnergyUnit.KILOWATT_HOUR: cls.from_kilowatt_hours,
            EnergyUnit.THERM: cls.from_therms,
        }
        return builders[resolved](value)

    @classmethod
    def parse(cls, text: str) -> Energy:
        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as an energy", field="energy")
        unit_text = match.group("unit").strip()
        if not unit_text:
            raise UnitError(f"{text!r} has no unit on it", field="energy")
        return cls.of(float(match.group("value")), unit_text)

    @property
    def mmbtu(self) -> float:
        return self.btu / _BTU_PER_MMBTU

    @property
    def megajoules(self) -> float:
        return self.btu / _BTU_PER_MJ

    @property
    def gigajoules(self) -> float:
        return self.megajoules / 1000.0

    @property
    def kilowatt_hours(self) -> float:
        return self.btu / _BTU_PER_KWH

    @property
    def therms(self) -> float:
        return self.btu / _BTU_PER_THERM

    def __add__(self, other: Energy) -> Energy:
        return Energy(self.btu + other.btu)

    def __mul__(self, factor: float) -> Energy:
        return Energy(self.btu * factor)

    def divided_by_efficiency(self, efficiency: float) -> Energy:
        """How much fuel it took to put this much heat in the steam."""

        if not 0.0 < efficiency <= 1.0:
            raise ValidationError(
                f"boiler efficiency has to sit in (0, 1], got {efficiency:g}",
                field="efficiency",
            )
        return Energy(self.btu / efficiency)

    def over(self, hours: float) -> EnergyRate:
        if hours <= 0:
            raise ValidationError("a run has to be longer than zero hours", field="hours")
        return EnergyRate(self.btu / hours)

    def __str__(self) -> str:
        if self.btu >= _BTU_PER_MMBTU:
            return f"{self.mmbtu:,.1f} MMBtu"
        return f"{self.btu:,.0f} Btu"


@dataclass(frozen=True, order=True)
class EnergyRate:
    """Heat per hour, held in Btu per hour."""

    btu_per_hour: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.btu_per_hour):
            raise ValidationError("energy rate is not finite", field="energy_rate")
        if self.btu_per_hour < 0:
            raise ValidationError("energy rate cannot be negative", field="energy_rate")

    @classmethod
    def from_btu_per_hour(cls, value: float) -> EnergyRate:
        return cls(value)

    @classmethod
    def from_kilowatts(cls, value: float) -> EnergyRate:
        return cls(value * _BTU_PER_HOUR_PER_KW)

    @classmethod
    def from_boiler_horsepower(cls, value: float) -> EnergyRate:
        return cls(value * _BTU_PER_BOILER_HORSEPOWER_HOUR)

    @property
    def mmbtu_per_hour(self) -> float:
        return self.btu_per_hour / _BTU_PER_MMBTU

    @property
    def kilowatts(self) -> float:
        return self.btu_per_hour / _BTU_PER_HOUR_PER_KW

    @property
    def boiler_horsepower(self) -> float:
        return self.btu_per_hour / _BTU_PER_BOILER_HORSEPOWER_HOUR

    def over(self, hours: float = HOURS_PER_YEAR) -> Energy:
        if hours < 0:
            raise ValidationError("hours cannot be negative", field="hours")
        return Energy(self.btu_per_hour * hours)

    def __add__(self, other: EnergyRate) -> EnergyRate:
        return EnergyRate(self.btu_per_hour + other.btu_per_hour)

    def __str__(self) -> str:
        return f"{self.btu_per_hour:,.0f} Btu/h"


@dataclass(frozen=True, order=True)
class SpecificEnthalpy:
    """Heat carried per pound of steam or water, in Btu per pound.

    This is the number a steam table hands back, and multiplying it by a leak
    rate is the whole point of the exercise.
    """

    btu_per_pound: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.btu_per_pound):
            raise ValidationError("enthalpy is not finite", field="enthalpy")

    @classmethod
    def from_btu_per_pound(cls, value: float) -> SpecificEnthalpy:
        return cls(value)

    @classmethod
    def from_kilojoules_per_kilogram(cls, value: float) -> SpecificEnthalpy:
        return cls(value / 2.326)

    @property
    def kilojoules_per_kilogram(self) -> float:
        return self.btu_per_pound * 2.326

    def carried_by(self, mass: Mass) -> Energy:
        return Energy(self.btu_per_pound * mass.pounds)

    def carried_at(self, flow: MassFlow) -> EnergyRate:
        return EnergyRate(self.btu_per_pound * flow.pounds_per_hour)

    def __sub__(self, other: SpecificEnthalpy) -> SpecificEnthalpy:
        return SpecificEnthalpy(self.btu_per_pound - other.btu_per_pound)

    def __add__(self, other: SpecificEnthalpy) -> SpecificEnthalpy:
        return SpecificEnthalpy(self.btu_per_pound + other.btu_per_pound)

    def __str__(self) -> str:
        return f"{self.btu_per_pound:,.1f} Btu/lb"
