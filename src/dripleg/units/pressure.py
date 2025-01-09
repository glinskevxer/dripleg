"""Pressure, carried as absolute and printed however the trade wants it.

Field paperwork is gauge and steam tables are absolute, and the two get mixed
up constantly. A 125 psig header is 139.7 psia, and Napier's formula wants the
absolute number. So the type stores psia, every constructor says which zero it
was handed, and nothing in the package passes a bare number around.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

from dripleg.errors import UnitError, ValidationError

__all__ = ["ATMOSPHERE_PSIA", "Pressure", "PressureUnit"]

ATMOSPHERE_PSIA = 14.695948775
"""One standard atmosphere. The gauge to absolute offset everywhere here."""

_PA_PER_PSI = 6894.757293168361
_PA_PER_BAR = 100000.0
_PSI_PER_BAR = _PA_PER_BAR / _PA_PER_PSI
_PA_PER_INHG = 3386.389
_PA_PER_INH2O = 249.0889

# A vacuum below this is not something a steam system does, and a negative
# absolute pressure is a data entry error rather than a reading.
_MIN_PSIA = 0.0


class PressureUnit(Enum):
    """The units a pressure is written in on a job sheet or a nameplate."""

    PSIG = "psig"
    PSIA = "psia"
    BARG = "barg"
    BARA = "bara"
    KPAA = "kpaa"
    KPAG = "kpag"
    INHG_VAC = "inhg_vac"
    INH2O_G = "inh2o"

    @property
    def is_gauge(self) -> bool:
        return self in {
            PressureUnit.PSIG,
            PressureUnit.BARG,
            PressureUnit.KPAG,
            PressureUnit.INH2O_G,
        }


_SPELLINGS = {
    "psig": PressureUnit.PSIG,
    "psi g": PressureUnit.PSIG,
    "psi": PressureUnit.PSIG,
    "psia": PressureUnit.PSIA,
    "psi a": PressureUnit.PSIA,
    "barg": PressureUnit.BARG,
    "bar g": PressureUnit.BARG,
    "bar": PressureUnit.BARG,
    "bara": PressureUnit.BARA,
    "bar a": PressureUnit.BARA,
    "kpa": PressureUnit.KPAG,
    "kpag": PressureUnit.KPAG,
    "kpa g": PressureUnit.KPAG,
    "kpaa": PressureUnit.KPAA,
    "kpa a": PressureUnit.KPAA,
    "inhg": PressureUnit.INHG_VAC,
    "in hg": PressureUnit.INHG_VAC,
    "inh2o": PressureUnit.INH2O_G,
    "in h2o": PressureUnit.INH2O_G,
    "inwc": PressureUnit.INH2O_G,
}

_TEXT = re.compile(r"^\s*(?P<value>[-+]?[0-9]*\.?[0-9]+)\s*(?P<unit>[a-zA-Z0-9 ]*)\s*$")


@dataclass(frozen=True, order=True)
class Pressure:
    """An absolute pressure. Construct it through one of the class methods."""

    psia: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.psia):
            raise ValidationError("pressure is not a finite number", field="pressure")
        if self.psia < _MIN_PSIA:
            raise ValidationError(
                f"absolute pressure cannot be negative, got {self.psia:g} psia",
                field="pressure",
            )

    # Constructors ---------------------------------------------------------

    @classmethod
    def from_psig(cls, value: float) -> Pressure:
        return cls(value + ATMOSPHERE_PSIA)

    @classmethod
    def from_psia(cls, value: float) -> Pressure:
        return cls(value)

    @classmethod
    def from_barg(cls, value: float) -> Pressure:
        return cls((value + 1.01325) * _PSI_PER_BAR)

    @classmethod
    def from_bara(cls, value: float) -> Pressure:
        return cls(value * _PSI_PER_BAR)

    @classmethod
    def from_kpa_absolute(cls, value: float) -> Pressure:
        return cls(value * 1000.0 / _PA_PER_PSI)

    @classmethod
    def from_kpa_gauge(cls, value: float) -> Pressure:
        return cls(value * 1000.0 / _PA_PER_PSI + ATMOSPHERE_PSIA)

    @classmethod
    def from_inches_mercury_vacuum(cls, value: float) -> Pressure:
        """Condenser and flash tank vacuum, written as inches of mercury below
        atmosphere and always quoted positive."""

        if value < 0:
            raise ValidationError("vacuum in inHg is quoted positive", field="pressure")
        return cls(ATMOSPHERE_PSIA - value * _PA_PER_INHG / _PA_PER_PSI)

    @classmethod
    def from_inches_water_gauge(cls, value: float) -> Pressure:
        return cls(value * _PA_PER_INH2O / _PA_PER_PSI + ATMOSPHERE_PSIA)

    @classmethod
    def of(cls, value: float, unit: PressureUnit | str) -> Pressure:
        """Build from a number and whatever the source called the unit."""

        resolved = cls._resolve(unit)
        builders = {
            PressureUnit.PSIG: cls.from_psig,
            PressureUnit.PSIA: cls.from_psia,
            PressureUnit.BARG: cls.from_barg,
            PressureUnit.BARA: cls.from_bara,
            PressureUnit.KPAA: cls.from_kpa_absolute,
            PressureUnit.KPAG: cls.from_kpa_gauge,
            PressureUnit.INHG_VAC: cls.from_inches_mercury_vacuum,
            PressureUnit.INH2O_G: cls.from_inches_water_gauge,
        }
        return builders[resolved](value)

    @classmethod
    def parse(cls, text: str) -> Pressure:
        """Read `"125 psig"` off a spreadsheet cell.

        A bare number is refused rather than guessed at. Half the gauge and
        absolute mix ups in this trade start with somebody assuming psig.
        """

        match = _TEXT.match(text)
        if match is None:
            raise ValidationError(f"cannot read {text!r} as a pressure", field="pressure")
        unit_text = match.group("unit").strip()
        if not unit_text:
            raise UnitError(f"{text!r} has no unit on it", field="pressure")
        return cls.of(float(match.group("value")), unit_text)

    @staticmethod
    def _resolve(unit: PressureUnit | str) -> PressureUnit:
        if isinstance(unit, PressureUnit):
            return unit
        key = " ".join(unit.lower().replace("_", " ").split())
        try:
            return _SPELLINGS[key]
        except KeyError:
            raise UnitError(f"unknown pressure unit {unit!r}", field="pressure") from None

    # Readings -------------------------------------------------------------

    @property
    def psig(self) -> float:
        return self.psia - ATMOSPHERE_PSIA

    @property
    def bara(self) -> float:
        return self.psia / _PSI_PER_BAR

    @property
    def barg(self) -> float:
        return self.bara - 1.01325

    @property
    def kpa_absolute(self) -> float:
        return self.psia * _PA_PER_PSI / 1000.0

    @property
    def kpa_gauge(self) -> float:
        return self.psig * _PA_PER_PSI / 1000.0

    @property
    def is_vacuum(self) -> bool:
        return self.psia < ATMOSPHERE_PSIA

    def ratio_to(self, other: Pressure) -> float:
        """Back pressure ratio, the thing that decides choked flow."""

        if other.psia <= 0:
            raise ValidationError("cannot take a pressure ratio against zero", field="pressure")
        return self.psia / other.psia

    def __str__(self) -> str:
        if self.is_vacuum:
            return f"{self.psia:.2f} psia"
        return f"{self.psig:.1f} psig"

    def __repr__(self) -> str:
        return f"Pressure(psia={self.psia:.6g})"
